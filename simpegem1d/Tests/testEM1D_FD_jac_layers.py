import unittest
from SimPEG import *
import matplotlib.pyplot as plt
from simpegem1d import EM1D, EM1DAnal, BaseEM1D


class EM1D_FD_Jac_layers_ProblemTests(unittest.TestCase):

    def setUp(self):

        FDsurvey = BaseEM1D.EM1DSurveyFD()
        FDsurvey.rxLoc = np.array([0., 0., 100.+1e-5])
        FDsurvey.txLoc = np.array([0., 0., 100.+1e-5])
        FDsurvey.fieldtype = 'secondary'

        nearthick = np.logspace(-1, 1, 2)
        deepthick = np.logspace(1, 2, 5)
        hx = np.r_[nearthick, deepthick]

        mesh1D = Mesh.TensorMesh([hx], [0.])
        depth = -mesh1D.gridN
        LocSigZ = -mesh1D.gridCC
        nlay = depth.size
        topo = np.r_[0., 0., 100.]
        FDsurvey.depth = depth
        FDsurvey.topo = topo
        FDsurvey.LocSigZ = LocSigZ

        FDsurvey.frequency = np.logspace(3, 3, 1)
        FDsurvey.Nfreq = FDsurvey.frequency.size
        FDsurvey.Setup1Dsystem()
        sig_half = 1e-1
        chi_half = 0.

        Logmodel = BaseEM1D.BaseEM1DModel(mesh1D)
        tau = 1e-3
        eta = 2e-1
        c = 1.
        options = {'Frequency': FDsurvey.frequency, 'tau': np.ones(nlay)*tau, 'eta':np.ones(nlay)*eta, 'c':np.ones(nlay)*c}
        Colemodel = BaseEM1D.BaseColeColeModel(mesh1D, **options)

        modelReal = Model.ComboModel(mesh1D, [Logmodel])
        modelComplex = Model.ComboModel(mesh1D, [Colemodel, Logmodel])
        m_1D = np.log(np.ones(nlay)*sig_half)

        FDsurvey.rxType = 'Hz'

        WT0 = np.load('../WT0.npy')
        WT1 = np.load('../WT1.npy')
        YBASE = np.load('../YBASE.npy')
        options = {'WT0': WT0, 'WT1': WT1, 'YBASE': YBASE}

        prob = EM1D.EM1D(modelReal, **options)
        prob.pair(FDsurvey)
        prob.chi = np.zeros(FDsurvey.nlay)


        self.survey = FDsurvey
        self.options = options
        self.modelReal = modelReal
        self.prob = prob
        self.mesh1D = mesh1D
        self.showIt = False


    def test_EM1DFDjac_Circ_RealCond_Layers(self):
        self.prob.CondType = 'Real'
        self.prob.survey.txType = 'CircularLoop'

        I = 1e0
        a = 1e1
        self.prob.survey.I = I
        self.prob.survey.a = a

        sig_half = np.r_[0.01]
        m_1D = np.log(np.ones(self.prob.survey.nlay)*sig_half)
        self.prob.jacSwitch = True
        Hz, dHzdsig = self.prob.fields(m_1D)
        dsigdm = self.prob.model.transformDeriv(m_1D)

        dHzdsig = dHzdsig*dsigdm

        def fwdfun(m):
            self.prob.jacSwitch = False
            Hz = self.prob.fields(m)
            return Hz

        def jacfun(m, dm):
            self.prob.jacSwitch = True
            Hz, dHzdsig = self.prob.fields(m)
            dsigdm = self.prob.model.transformDeriv(m)
            return np.dot(dHzdsig, dsigdm*dm)

        def jacfunpert(m, dm):
            self.prob.jacSwitch = False
            dHzdsig = np.zeros((self.prob.survey.Nfreq, m.size), dtype = complex)
            m1 = np.zeros(m.size)
            m2 = np.zeros(m.size)
            perc = 0.001
            for i in range (m.size):
                m1 = m.copy()
                m2 = m.copy()
                m1[i] = m[i]+perc*m[i]
                m2[i] = m[i]-perc*m[i]
                Hzu = self.prob.fields(m1)
                Hzd = self.prob.fields(m2)
                dHzdsig[:, i] = (Hzu-Hzd)/(2*perc*m[i])
            return dHzdsig, np.dot(dHzdsig, (dm))


        dHzdsiganal = jacfunpert(m_1D, 0.)[0]
        for i in range(self.prob.survey.nlay):
            print i, abs((Utils.mkvc(dHzdsig)[i].imag-Utils.mkvc(dHzdsiganal)[i].imag)/Utils.mkvc(dHzdsiganal)[i].imag)
            # print i, abs((Utils.mkvc(dHzdsig)[i].real-Utils.mkvc(dHzdsiganal)[i].real)/Utils.mkvc(dHzdsiganal)[i].real)

        passed = True

        dm = m_1D*0.5
        # derChk = lambda m: [fwdfun(m), lambda mx: jacfun(m, mx)]
        derChk = lambda m: [fwdfun(m), lambda mx: jacfunpert(m, mx)[1]]
        passed = Tests.checkDerivative(derChk, m_1D, num=4, dx = dm, plotIt=False)
        if passed:
            print "EM1DFD-CircularLoop for real conductivity works"


if __name__ == '__main__':
    unittest.main()