from SimPEG import *
import BaseEM1D
# from future import division
from scipy.constants import mu_0
# from Kernels import HzKernel_layer, HzkernelCirc_layer
from DigFilter import EvalDigitalFilt
from RTEfun import rTEfun
# from numba import jit

class EM1D(Problem.BaseProblem):
    """
        Pseudo analytic solutions for frequency and time domain EM problems assuming
        Layered earth (1D).
    """
    surveyPair = BaseEM1D.BaseEM1DSurvey
    modelPair = BaseEM1D.BaseEM1DModel
    # modelPair = Model.BaseModel
    CondType = 'Real'
    WT1 = None
    WT0 = None
    YBASE = None
    chi = None
    M00 = None
    M10 = None
    M01 = None
    M11 = None
    jacSwitch = False


    def __init__(self, model, **kwargs):

        Problem.BaseProblem.__init__(self, model, **kwargs)
        self.WT0 = kwargs['WT0']
        self.WT1 = kwargs['WT1']
        self.YBASE = kwargs['YBASE']
        self.drTE = []

    def HzKernel_layer(self, lamda, f, nlay, sig, chi, depth, h, z, flag):

        """

            Kernel for vertical magnetic component (Hz) due to vertical magnetic
            diopole (VMD) source in (kx,ky) domain

        """
        u0 = lamda
        rTE = np.zeros(lamda.size, dtype=complex)
        drTE = np.zeros((nlay, lamda.size), dtype=complex)

        rTE, drTE = rTEfun(nlay, f, lamda, sig, chi, depth, self.survey.HalfSwitch)

        if flag=='secondary':
            # Note
            # Here only computes secondary field.
            # I am not sure why it does not work if we add primary term.
            # This term can be analytically evaluated, where h = 0.

            kernel = 1/(4*np.pi)*(rTE*np.exp(-u0*(z+h)))*lamda**3/u0

        else:
            kernel = 1/(4*np.pi)*(np.exp(u0*(z-h))+ rTE*np.exp(-u0*(z+h)))*lamda**3/u0

        if self.jacSwitch == True:
            jackernel = 1/(4*np.pi)*(drTE)*(np.exp(-u0*(z+h))*lamda**3/u0)
            Kernel = []
            Kernel.append(kernel)
            Kernel.append(jackernel)

        else:

            Kernel = kernel


        return  Kernel

    @Utils.requires('survey')
    def HzkernelCirc_layer(self, lamda, f, nlay, sig, chi, depth, h, z, I, a, flag):

        """

            Kernel for vertical magnetic component (Hz) at the center
            due to circular loop source in (kx,ky) domain

            .. math::

                H_z = \\frac{Ia}{2} \int_0^{\infty} [e^{-u_0|z+h|} + r_{TE}e^{u_0|z-h|}] \\frac{\lambda^2}{u_0} J_1(\lambda a)] d \lambda

        """

        w = 2*np.pi*f
        rTE = np.zeros(lamda.size, dtype=complex)
        rTE = np.zeros((nlay, lamda.size), dtype=complex)
        u0 = lamda
        rTE, drTE = rTEfun(nlay, f, lamda, sig, chi, depth, self.survey.HalfSwitch)


        if flag == 'secondary':
            kernel = I*a*0.5*(rTE*np.exp(-u0*(z+h)))*lamda**2/u0
        else:
            kernel = I*a*0.5*(np.exp(u0*(z-h))+rTE*np.exp(-u0*(z+h)))*lamda**2/u0

        if self.jacSwitch == True:
            jackernel = I*a*0.5*(drTE)*(np.exp(-u0*(z+h))*lamda**2/u0)
            Kernel = []
            Kernel.append(kernel)
            Kernel.append(jackernel)
        else:

            Kernel = kernel

        return  Kernel

    @Utils.requires('survey')
    def fields(self, m):
        """
            Return Bz or dBzdt

            .. math ::

        """

        f = self.survey.frequency
        nfreq = self.survey.Nfreq
        flag = self.survey.fieldtype
        r = self.survey.offset
        sig = self.model.transform(m)
        #TODO: In corporate suseptibility in to the model !!
        chi = self.chi
        nlay = self.survey.nlay
        depth = self.survey.depth
        h = self.survey.h
        z = self.survey.z
        HzFHT = np.zeros(nfreq, dtype = complex)
        dHzFHTdsig = np.zeros((nlay, nfreq), dtype = complex)

        if self.jacSwitch==True:
            if self.CondType == 'Real':
                    if self.survey.txType == 'VMD':
                        r = self.survey.offset
                        for ifreq in range(nfreq):
                            kernel    = lambda x: self.HzKernel_layer(x, f[ifreq], nlay, sig, chi, depth, h, z, flag)[0]
                            jackernel = lambda x: self.HzKernel_layer(x, f[ifreq], nlay, sig, chi, depth, h, z, flag)[1]
                            HzFHT[ifreq] = EvalDigitalFilt(self.YBASE, self.WT0, kernel, r)
                            dHzFHTdsig[:,ifreq] = EvalDigitalFilt(self.YBASE, self.WT0, jackernel, r)

                    elif self.survey.txType == 'CircularLoop':
                        I = self.survey.I
                        a = self.survey.a
                        for ifreq in range(nfreq):
                            kernel    = lambda x: self.HzkernelCirc_layer(x, f[ifreq], nlay, sig, chi, depth, h, z, I, a, flag)[0]
                            jackernel = lambda x: self.HzkernelCirc_layer(x, f[ifreq], nlay, sig, chi, depth, h, z, I, a, flag)[1]
                            HzFHT[ifreq] = EvalDigitalFilt(self.YBASE, self.WT1, kernel, a)
                            dHzFHTdsig[:,ifreq] = EvalDigitalFilt(self.YBASE, self.WT1, jackernel, a)
                    else :
                        raise Exception("Tx options are only VMD or CircularLoop!!")

            elif self.CondType == 'Complex':
                sig_temp = np.zeros(self.survey.nlay, dtype = complex)
                if self.survey.txType == 'VMD':
                    r = self.survey.offset
                    for ifreq in range(nfreq):
                        sig_temp = Utils.mkvc(sig[ifreq, :])
                        kernel = lambda x: self.HzKernel_layer(x, f[ifreq], nlay, sig_temp, chi, depth, h, z, flag)[0]
                        jackernel = lambda x: self.HzKernel_layer(x, f[ifreq], nlay, sig_temp, chi, depth, h, z, flag)[1]
                        HzFHT[ifreq] = EvalDigitalFilt(self.YBASE, self.WT0, kernel, r)
                        dHzFHTdsig[:,ifreq] = EvalDigitalFilt(self.YBASE, self.WT0, jackernel, r)

                elif self.survey.txType == 'CircularLoop':
                    I = self.survey.I
                    a = self.survey.a
                    for ifreq in range(nfreq):
                        sig_temp = Utils.mkvc(sig[ifreq, :])
                        kernel = lambda x: self.HzkernelCirc_layer(x, f[ifreq], nlay, sig_temp, chi, depth, h, z, I, a, flag)[0]
                        jackernel = lambda x: self.HzkernelCirc_layer(x, f[ifreq], nlay, sig_temp, chi, depth, h, z, I, a, flag)[1]
                        dHzFHTdsig[:,ifreq] = EvalDigitalFilt(self.YBASE, self.WT1, jackernel, a)
                else :
                    raise Exception("Tx options are only VMD or CircularLoop!!")
            else :

                raise Exception("CondType should be either 'Real' or 'Complex'!!")

            if nlay==1:
                dHzFHTdsig = Utils.mkvc(dHzFHTdsig)
            return  HzFHT, dHzFHTdsig.T
            # return  HzFHT

        else:
            if self.CondType == 'Real':
                if self.survey.txType == 'VMD':
                    r = self.survey.offset
                    for ifreq in range(nfreq):
                        kernel = lambda x: self.HzKernel_layer(x, f[ifreq], nlay, sig, chi, depth, h, z, flag)
                        HzFHT[ifreq] = EvalDigitalFilt(self.YBASE, self.WT0, kernel, r)

                elif self.survey.txType == 'CircularLoop':
                    I = self.survey.I
                    a = self.survey.a
                    for ifreq in range(nfreq):
                        kernel = lambda x: self.HzkernelCirc_layer(x, f[ifreq], nlay, sig, chi, depth, h, z, I, a, flag)
                        HzFHT[ifreq] = EvalDigitalFilt(self.YBASE, self.WT1, kernel, a)
                else :
                    raise Exception("Tx options are only VMD or CircularLoop!!")

            elif self.CondType == 'Complex':
                sig_temp = np.zeros(self.survey.nlay, dtype = complex)
                if self.survey.txType == 'VMD':
                    r = self.survey.offset
                    for ifreq in range(nfreq):
                        sig_temp = Utils.mkvc(sig[ifreq, :])
                        kernel = lambda x: self.HzKernel_layer(x, f[ifreq], nlay, sig_temp, chi, depth, h, z, flag)
                        HzFHT[ifreq] = EvalDigitalFilt(self.YBASE, self.WT0, kernel, r)

                elif self.survey.txType == 'CircularLoop':
                    I = self.survey.I
                    a = self.survey.a
                    for ifreq in range(nfreq):
                        sig_temp = Utils.mkvc(sig[ifreq, :])
                        kernel = lambda x: self.HzkernelCirc_layer(x, f[ifreq], nlay, sig_temp, chi, depth, h, z, I, a, flag)
                        HzFHT[ifreq] = EvalDigitalFilt(self.YBASE, self.WT1, kernel, a)
                else :
                    raise Exception("Tx options are only VMD or CircularLoop!!")
            else :

                raise Exception("CondType should be either 'Real' or 'Complex'!!")


            return  HzFHT


    @Utils.timeIt
    def Jtvec(self, m, v, u=None):
        """
            Computing Jacobian^T multiplied by vector.

        """
        pass


if __name__ == '__main__':
    # hx = np.ones(10)
    # M = Mesh.TensorMesh([hx])

    # model = Model.LogModel(M)
    # prob = EM1D(M)

    test1 = np.load('WT1.npy')
    test2 = np.load('WT0.npy')