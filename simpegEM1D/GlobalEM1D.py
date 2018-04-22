try:
    from multiprocessing import Pool
except ImportError:
    print ("multiprocessing is not available")
    PARALLEL = False
else:
    PARALLEL = True
    import multiprocessing

import numpy as np
import scipy.sparse as sp
from SimPEG import Problem, Props, Utils, Maps, Survey
from .Survey import EM1DSurveyFD, EM1DSurveyTD
from .EM1DSimulation import run_simulation_FD, run_simulation_TD
import properties
import warnings


def dot(args):
    return np.dot(args[0], args[1])


class GlobalEM1DProblem(Problem.BaseProblem):
    """
        The GlobalProblem allows you to run a whole bunch of SubProblems,
        potentially in parallel, potentially of different meshes.
        This is handy for working with lots of sources,
    """
    sigma, sigmaMap, sigmaDeriv = Props.Invertible(
        "Electrical conductivity (S/m)"
    )

    _Jmatrix = None
    run_simulation = None
    n_cpu = None
    hz = None
    parallel = False
    parallel_jvec_jtvec = False
    verbose = False
    fix_Jmatrix = False

    def __init__(self, mesh, **kwargs):
        Utils.setKwargs(self, **kwargs)
        self.mesh = mesh
        if PARALLEL:
            if self.parallel:
                print (">> Use multiprocessing for parallelization")
                if self.n_cpu is None:
                    self.n_cpu = multiprocessing.cpu_count()
                print ((">> n_cpu: %i")%(self.n_cpu))
            else:
                print (">> Serial version is used")
        else:
            print (">> Serial version is used")
        if self.hz is None:
            raise Exception("Input vertical thickness hz !")

    @property
    def n_layer(self):
        return self.hz.size

    @property
    def n_sounding(self):
        return self.survey.n_sounding

    @property
    def rx_locations(self):
        return self.survey.rx_locations

    @property
    def src_locations(self):
        return self.survey.src_locations

    @property
    def data_index(self):
        return self.survey.data_index

    @property
    def topo(self):
        return self.survey.topo

    @property
    def offset(self):
        return self.survey.offset

    @property
    def a(self):
        return self.survey.a

    @property
    def I(self):
        return self.survey.I

    @property
    def field_type(self):
        return self.survey.field_type

    @property
    def rx_type(self):
        return self.survey.rx_type

    @property
    def src_type(self):
        return self.survey.src_type

    @property
    def half_switch(self):
        return self.survey.half_switch

    @property
    def Sigma(self):
        if getattr(self, '_Sigma', None) is None:
            # Ordering: first z then x
            self._Sigma = self.sigma.reshape((self.n_sounding, self.n_layer))
        return self._Sigma

    def fields(self, m):
        if self.verbose:
            print ("Compute fields")
        self.survey._pred = self.forward(m)
        return []

    def Jvec(self, m, v, f=None):
        J = self.getJ(m)
        if self.parallel and self.parallel_jvec_jtvec:
            V = v.reshape((self.n_sounding, self.n_layer))

            pool = Pool(self.n_cpu)
            Jv = np.hstack(
                pool.map(
                    dot,
                    [(J[i], V[i, :]) for i in range(self.n_sounding)]
                )
            )
            pool.close()
            pool.join()
        else:
            return J * v
        return Jv

    def Jtvec(self, m, v, f=None):
        J = self.getJ(m)
        if self.parallel and self.parallel_jvec_jtvec:
            pool = Pool(self.n_cpu)

            Jtv = np.hstack(
                pool.map(
                    dot,
                    [(J[i].T, v[self.data_index[i]]) for i in range(self.n_sounding)]
                )
            )
            pool.close()
            pool.join()
            return Jtv
        else:

            return J.T*v

    @property
    def deleteTheseOnModelUpdate(self):
        toDelete = []
        if self.sigmaMap is not None:
            toDelete += ['_Sigma']
        if self.fix_Jmatrix is False:
            if self._Jmatrix is not None:
                toDelete += ['_Jmatrix']
        return toDelete


class GlobalEM1DProblemFD(GlobalEM1DProblem):

    run_simulation = run_simulation_FD

    @property
    def frequency(self):
        return self.survey.frequency

    @property
    def switch_real_imag(self):
        return self.survey.switch_real_imag

    def input_args(self, i_sounding, jacSwitch=False):
        output = (
            self.rx_locations[i_sounding, :],
            self.src_locations[i_sounding, :],
            self.topo[i_sounding, :], self.hz,
            self.offset, self.frequency,
            self.field_type, self.rx_type, self.src_type,
            self.Sigma[i_sounding, :], jacSwitch
        )
        return output

    def forward(self, m):
        self.model = m

        if self.verbose:
            print (">> Compute response")

        if self.parallel:
            pool = Pool(self.n_cpu)
            # This assumes the same # of layer for each of soundings
            result = pool.map(
                run_simulation_FD,
                [
                    self.input_args(i, jacSwitch=False) for i in range(self.n_sounding)
                ]
            )
            pool.close()
            pool.join()
        else:
            result = [
                run_simulation_FD(self.input_args(i, jacSwitch=False)) for i in range(self.n_sounding)
            ]
        return np.hstack(result)

    def getJ(self, m):
        """
             Compute d F / d sigma
        """
        if self._Jmatrix is not None:
            return self._Jmatrix
        if self.verbose:
            print (">> Compute J")
        self.model = m
        if self.parallel:
            pool = Pool(self.n_cpu)
            self._Jmatrix = pool.map(
                run_simulation_FD,
                [
                    self.input_args(i, jacSwitch=True) for i in range(self.n_sounding)
                ]
            )
            pool.close()
            pool.join()
            if self.parallel_jvec_jtvec is False:
                self._Jmatrix = sp.block_diag(self._Jmatrix).tocsr()
        else:
            # _Jmatrix is block diagnoal matrix (sparse)
            self._Jmatrix = sp.block_diag(
                [
                    run_simulation_FD(self.input_args(i, jacSwitch=True)) for i in range(self.n_sounding)
                ]
            ).tocsr()
        return self._Jmatrix


class GlobalEM1DProblemTD(GlobalEM1DProblem):

    run_simulation = run_simulation_TD

    @property
    def wave_type(self):
        return self.survey.wave_type

    @property
    def input_currents(self):
        return self.survey.input_currents

    @property
    def time_input_currents(self):
        return self.survey.time_input_currents

    @property
    def n_pulse(self):
        return self.survey.n_pulse

    @property
    def base_frequency(self):
        return self.survey.base_frequency

    @property
    def time(self):
        return self.survey.time

    @property
    def use_lowpass_filter(self):
        return self.survey.use_lowpass_filter

    @property
    def high_cut_frequency(self):
        return self.survey.high_cut_frequency

    @property
    def moment_type(self):
        return self.survey.moment_type

    @property
    def time_dual_moment(self):
        return self.survey.time_dual_moment

    @property
    def time_input_currents_dual_moment(self):
        return self.survey.time_input_currents_dual_moment

    @property
    def input_currents_dual_moment(self):
        return self.survey.input_currents_dual_moment

    @property
    def base_frequency_dual_moment(self):
        return self.survey.base_frequency_dual_moment

    def input_args(self, i_sounding, jacSwitch=False):
        output = (
            self.rx_locations[i_sounding, :],
            self.src_locations[i_sounding, :],
            self.topo[i_sounding, :],
            self.hz,
            self.time[i_sounding],
            self.field_type[i_sounding],
            self.rx_type[i_sounding],
            self.src_type[i_sounding],
            self.wave_type[i_sounding],
            self.offset[i_sounding],
            self.a[i_sounding],
            self.time_input_currents[i_sounding],
            self.input_currents[i_sounding],
            self.n_pulse[i_sounding],
            self.base_frequency[i_sounding],
            self.use_lowpass_filter[i_sounding],
            self.high_cut_frequency[i_sounding],
            self.moment_type[i_sounding],
            self.time_dual_moment[i_sounding],
            self.time_input_currents_dual_moment[i_sounding],
            self.input_currents_dual_moment[i_sounding],
            self.base_frequency_dual_moment[i_sounding],
            self.Sigma[i_sounding, :],
            jacSwitch
        )
        return output

    def forward(self, m, f=None):
        self.model = m

        if self.parallel:
            pool = Pool(self.n_cpu)
            # This assumes the same # of layer for each of soundings
            result = pool.map(
                run_simulation_TD,
                [
                    self.input_args(i, jacSwitch=False) for i in range(self.n_sounding)
                ]
            )
            pool.close()
            pool.join()
        else:
            result = [
                run_simulation_TD(self.input_args(i, jacSwitch=False)) for i in range(self.n_sounding)
            ]
        return np.hstack(result)

    def getJ(self, m):
        """
             Compute d F / d sigma
        """
        if self._Jmatrix is not None:
            return self._Jmatrix
        if self.verbose:
            print (">> Compute J")
        self.model = m
        if self.parallel:
            pool = Pool(self.n_cpu)
            self._Jmatrix = pool.map(
                run_simulation_TD,
                [
                    self.input_args(i, jacSwitch=True) for i in range(self.n_sounding)
                ]
            )
            pool.close()
            pool.join()
            if self.parallel_jvec_jtvec is False:
                self._Jmatrix = sp.block_diag(self._Jmatrix).tocsr()
        else:
            # _Jmatrix is block diagnoal matrix (sparse)
            self._Jmatrix = sp.block_diag(
                [
                    run_simulation_TD(self.input_args(i, jacSwitch=True)) for i in range(self.n_sounding)
                ]
            ).tocsr()
        return self._Jmatrix


class GlobalEM1DSurvey(Survey.BaseSurvey, properties.HasProperties):

    # This assumes a multiple sounding locations
    rx_locations = properties.Array(
        "Receiver locations ", dtype=float, shape=('*', 3)
    )
    src_locations = properties.Array(
        "Source locations ", dtype=float, shape=('*', 3)
    )
    topo = properties.Array(
        "Topography", dtype=float, shape=('*', 3)
    )

    _pred = None

    @Utils.requires('prob')
    def dpred(self, m, f=None):
        """
            Return predicted data.
            Predicted data, (`_pred`) are computed when
            self.prob.fields is called.
        """
        if f is None:
            f = self.prob.fields(m)

        return self._pred

    @property
    def n_sounding(self):
        """
            # of Receiver locations
        """
        return self.rx_locations.shape[0]

    @property
    def n_layer(self):
        """
            # of Receiver locations
        """
        return self.prob.n_layer

    def read_xyz_data(self, fname):
        """
        Read csv file format
        This is a place holder at this point
        """
        pass


class GlobalEM1DSurveyFD(GlobalEM1DSurvey, EM1DSurveyFD):

    @property
    def nD(self):
        if self.switch_real_imag == "all":
            return int(self.n_frequency * 2) * self.n_sounding
        elif (
            self.switch_real_imag == "imag" or self.switch_real_imag == "real"
        ):
            return int(self.n_frequency) * self.n_sounding

    def read_xyz_data(self, fname):
        """
        Read csv file format
        This is a place holder at this point
        """
        pass


class GlobalEM1DSurveyTD(GlobalEM1DSurvey):

    # --------------- Essential inputs ---------------- #
    src_type = None

    rx_type = None

    field_type = None

    time = []

    wave_type = None

    moment_type = None

    time_input_currents = []

    input_currents = []

    # --------------- Selective inputs ---------------- #
    n_pulse = properties.Array(
        "The number of pulses",
        default=None
    )

    base_frequency = properties.Array(
        "Base frequency (Hz)",
        dtype=float, default=None
    )

    offset = properties.Array(
        "Src-Rx offsets", dtype=float, default=None,
        shape=('*', '*')
    )

    I = properties.Array(
        "Src loop current", dtype=float, default=None
    )

    a = properties.Array(
        "Src loop radius", dtype=float, default=None
    )

    use_lowpass_filter = properties.Array(
        "Switch for low pass filter",
        dtype=bool, default=None
    )

    high_cut_frequency = properties.Array(
        "High cut frequency for low pass filter (Hz)",
        dtype=float, default=None
    )

    # ------------- For dual moment ------------- #

    time_dual_moment = []

    time_input_currents_dual_moment = []

    input_currents_dual_moment = []

    base_frequency_dual_moment = properties.Array(
        "Base frequency for the dual moment (Hz)",
        dtype=float, default=None
    )

    def __init__(self, **kwargs):
        GlobalEM1DSurvey.__init__(self, **kwargs)
        self.set_parameters()

    def set_parameters(self):
        # TODO: need to put some validation process
        # e.g. for VMD `offset` must be required
        # e.g. for CircularLoop `a` must be required

        print (">> Set parameters")
        if self.n_pulse is None:
            self.n_pulse = np.ones(self.n_sounding, dtype=int) * 2

        if self.base_frequency is None:
            self.base_frequency = np.ones(
                (self.n_sounding), dtype=float
            ) * 30

        if self.offset is None:
            self.offset = np.empty((self.n_sounding, 1), dtype=float)

        if self.I is None:
            self.I = np.empty(self.n_sounding, dtype=float)

        if self.a is None:
            self.a = np.empty(self.n_sounding, dtype=float)

        if self.use_lowpass_filter is None:
            self.use_lowpass_filter = np.zeros(self.n_sounding, dtype=bool)

        if self.high_cut_frequency is None:
            self.high_cut_frequency = np.empty(self.n_sounding, dtype=float)

        if self.moment_type is None:
            self.moment_type = np.array(["single"], dtype=str).repeat(
                self.n_sounding, axis=0
            )

        # List
        if not self.time_input_currents:
            self.time_input_currents = [
                np.empty(1, dtype=float) for i in range(self.n_sounding)
            ]
        # List
        if not self.input_currents:
            self.input_currents = [
                np.empty(1, dtype=float) for i in range(self.n_sounding)
            ]

        # List
        if not self.time_dual_moment:
            self.time_dual_moment = [
                np.empty(1, dtype=float) for i in range(self.n_sounding)
            ]
        # List
        if not self.time_input_currents_dual_moment:
            self.time_input_currents_dual_moment = [
                np.empty(1, dtype=float) for i in range(self.n_sounding)
            ]
        # List
        if not self.input_currents_dual_moment:
            self.input_currents_dual_moment = [
                np.empty(1, dtype=float) for i in range(self.n_sounding)
            ]

        if self.base_frequency_dual_moment is None:
            self.base_frequency_dual_moment = np.empty(
                (self.n_sounding), dtype=float
            )

    @property
    def nD_vec(self):
        # Need to generalize this for the dual moment data
        if getattr(self, '_nD_vec', None) is None:
            self._nD_vec = np.array(
                [time.size for time in self.time], dtype=int
            )
        return self._nD_vec

    @property
    def data_index(self):
        # Need to generalize this for the dual moment data
        if getattr(self, '_data_index', None) is None:
            self._data_index = [
                    np.arange(self.nD_vec[i_sounding])+np.sum(self.nD_vec[:i_sounding]) for i_sounding in range(self.n_sounding)
            ]
        return self._data_index

    @property
    def nD(self):
        # Need to generalize this for the dual moment data
        if getattr(self, '_nD', None) is None:
            self._nD = self.nD_vec.sum()
        return self._nD