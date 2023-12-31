# coding=utf-8
"""
20210810
Zhang Ji

problem class, organize the problem.
"""
import abc
import pickle
import logging
from tqdm import tqdm
import numpy as np
from tqdm.notebook import tqdm as tqdm_notebook
from petsc4py import PETSc
from datetime import datetime
import time
import shutil
import os
import h5py
from matplotlib import pyplot as plt

from act_src import baseClass
from act_src import particleClass
from act_src import interactionClass
from act_src import relationClass
from act_codeStore.support_class import *
from act_codeStore import support_fun as spf


class _baseProblem(baseClass.baseObj):
    def __init__(self, name = '...', tqdm_fun = tqdm_notebook, **kwargs):
        super().__init__(name, **kwargs)
        # self._type = 'baseProblem'
        self._dimension = -1  # -1 for undefined, 2 for 2D, 3 for 3D
        self._rot_noise = 0  # rotational noise
        self._trs_noise = 0  # translational noise
        self._obj_list = uniqueList(acceptType = particleClass._baseParticle)  # contain objects
        self._action_list = uniqueList(
            acceptType = interactionClass._baseAction)  # contain rotational interactions
        self._Xall = np.nan  # location at current time
        self._Wall = np.nan  # rotational velocity at current time
        self._Uall = np.nan  # translational velocity at current time
        self._relationHandle = relationClass._baseRelation()
        self._pickle_name = os.path.join(self.name, 'pickle.%s' % self.name)
        self._log_name = os.path.join(self.name, 'log.%s' % self.name)
        self._logger = None
        # self._logger = logging.getLogger()
        # self._hdf5 = None
        self._hdf5_name = os.path.join(self.name, 'hdf5.%s' % self.name)
        self._hdf5_kwargs = {
            'chunks': True,
            # 'compression': 'lzf',
            # 'compression_opts': 9,
            }

        # clear dir
        fileHandle = self.name
        tprint = False
        if self.rank0:
            fileHandle = self.name
            self._logger = logging.getLogger()
            if os.path.exists(fileHandle) and os.path.isdir(fileHandle):
                shutil.rmtree(fileHandle)
                tprint = True
            os.makedirs(fileHandle)
            #
            logging.basicConfig(handlers = [logging.FileHandler(filename = self.log_name, mode = 'w'),
                                            logging.StreamHandler()],
                                level = logging.INFO,
                                format = '%(message)s', )
        time.sleep(0.1)
        #
        if tprint:
            spf.petscInfo(self.logger, 'remove folder %s' % fileHandle)
        spf.petscInfo(self.logger, 'make folder %s' % fileHandle)
        spf.petscInfo(self.logger, ' ')
        spf.petscInfo(self.logger, 'Collective motion solve, Zhang Ji, 2021. ')

        # parameters for temporal evaluation.
        self._save_every = 1
        self._do_save = True
        self._tqdm_fun = tqdm_fun
        self._tqdm = None
        self._update_fun = '3bs'  # funHandle and order
        self._update_order = (1e-6, 1e-9)  # rtol, atol
        self._t0 = 0  # simulation time in the range (t0, t1)
        self._t1 = -1  # simulation time in the range (t0, t1)
        self._eval_dt = -1  # \delta_t, time step of simulation
        self._save_dt = -1  # \delta_t, time step of date saving
        self._max_it = -1  # iteration loop no more than max_it
        self._percentage = 0  # percentage of time depend solver
        self._t_hist = []
        self._dt_hist = []
        self._tmp_idx = []  # temporary globe idx
        self._update_start_time = 0
        self._update_stop_time = 0

    @property
    def dimension(self):
        return self._dimension

    @property
    def rot_noise(self):
        return self._rot_noise

    @rot_noise.setter
    def rot_noise(self, rot_noise):
        self._rot_noise = rot_noise

    @property
    def trs_noise(self):
        return self._trs_noise

    @trs_noise.setter
    def trs_noise(self, trs_noise):
        self._trs_noise = trs_noise

    @property
    def action_list(self):
        return self._action_list

    @property
    def obj_list(self):
        return self._obj_list

    @property
    def Uall(self):
        return self._Uall

    @Uall.setter
    def Uall(self, Uall):
        self._Uall = Uall

    @property
    def Wall(self):
        return self._Wall

    @Wall.setter
    def Wall(self, Wall):
        self._Wall = Wall

    @property
    def Xall(self):
        return self._Xall

    @Xall.setter
    def Xall(self, Xall):
        self._Xall = Xall

    @property
    def relationHandle(self):
        return self._relationHandle

    @relationHandle.setter
    def relationHandle(self, relationHandle):
        self._check_relationHandle(relationHandle)
        relationHandle.father = self
        self._relationHandle = relationHandle

    @property
    def pickle_name(self):
        return self._pickle_name

    @property
    def log_name(self):
        return self._log_name

    @property
    def logger(self):
        return self._logger

    # @property
    # def hdf5(self):
    #     return self._hdf5

    @property
    def hdf5_name(self):
        return self._hdf5_name

    @property
    def hdf5_kwargs(self):
        return self._hdf5_kwargs

    @property
    def save_every(self):
        return self._save_every

    @save_every.setter
    def save_every(self, save_every):
        self._save_every = int(save_every)

    @property
    def do_save(self):
        return self._do_save

    @do_save.setter
    def do_save(self, do_save):
        self._do_save = bool(do_save)

    @property
    def tqdm_fun(self):
        return self._tqdm_fun

    @tqdm_fun.setter
    def tqdm_fun(self, tqdm_fun):
        self._tqdm_fun = tqdm_fun

    @property
    def tqdm(self):
        return self._tqdm

    @tqdm.setter
    def tqdm(self, mytqdm):
        err_msg = 'wrong parameter type tqdm. '
        assert isinstance(mytqdm, tqdm), err_msg
        self._tqdm = mytqdm

    @property
    def update_fun(self):
        return self._update_fun

    @update_fun.setter
    def update_fun(self, update_fun):
        assert update_fun in ("1fe", "2a", "3", "3bs", "4", "5f",
                              "5dp", "5bs", "6vr", "7vr", "8vr")
        self._update_fun = update_fun

    @property
    def update_order(self):
        return self._update_order

    @update_order.setter
    def update_order(self, update_order):
        assert len(update_order) == 2
        self._update_order = update_order

    @property
    def rtol(self):
        return self.update_order[0]

    @property
    def atol(self):
        return self.update_order[1]

    @property
    def t0(self):
        return self._t0

    @t0.setter
    def t0(self, t0):
        self._t0 = t0

    @property
    def t1(self):
        return self._t1

    @t1.setter
    def t1(self, t1):
        self._t1 = t1

    @property
    def eval_dt(self):
        return self._eval_dt

    @eval_dt.setter
    def eval_dt(self, eval_dt):
        self._eval_dt = eval_dt

    @property
    def max_it(self):
        return self._max_it

    @max_it.setter
    def max_it(self, max_it):
        self._max_it = max_it

    @property
    def percentage(self):
        return self._percentage

    @percentage.setter
    def percentage(self, percentage):
        self._percentage = percentage

    @property
    def t_hist(self):
        return self._t_hist

    @property
    def dt_hist(self):
        return self._dt_hist

    @property
    def tmp_idx(self):
        return self._tmp_idx

    @property
    def n_obj(self):
        return len(self.obj_list)

    @property
    def polar(self) -> np.asarray:
        polar = np.linalg.norm(np.sum([obji.P1 for obji in self.obj_list], axis = 0)) / self.n_obj
        return polar

    @property
    def milling_Daniel2014(self) -> np.asarray:
        t1 = [np.cross(obji.X, obji.P1) / np.linalg.norm(obji.X) for obji in self.obj_list]
        milling = np.linalg.norm(np.sum(t1, axis = 0)) / self.n_obj
        return milling

    @property
    def speed(self) -> np.asarray:
        speed = np.sum([np.linalg.norm(obji.U) for obji in self.obj_list], axis = 0) / self.n_obj
        return speed

    def _check_add_obj(self, obj):
        err_msg = 'wrong object type'
        assert isinstance(obj, particleClass._baseParticle), err_msg
        err_msg = 'wrong dimension'
        assert np.isclose(self.dimension, obj.dimension), err_msg
        return True

    def add_obj(self, obj: "particleClass._baseParticle"):
        self._check_add_obj(obj)
        obj.index = self.n_obj
        obj.father = self
        obj.rot_noise = self.rot_noise
        obj.trs_noise = self.trs_noise
        self._obj_list.append(obj)
        return True

    def _check_add_act(self, act):
        # err_msg = 'wrong object type'
        # assert isinstance(act, interaction.WAction), err_msg
        pass

    def add_act(self, act: "interactionClass._baseAction", add_all_obj = True):
        self._check_add_act(act)
        self.action_list.append(act)
        act.father = self
        if add_all_obj:
            for obji in self.obj_list:
                act.add_obj(obji)
        return True

    @staticmethod
    def _check_relationHandle(pos: "relationClass._baseRelation"):
        err_msg = 'wrong object type'
        assert isinstance(pos, relationClass._baseRelation), err_msg
        # pass

    def update_prepare(self, showInfo = True):
        # location
        self._obj_list = np.array(self.obj_list)
        self.Xall = np.vstack([objj.X for objj in self.obj_list])
        # self.Uall = np.vstack([objj.U for objj in self.obj_list])
        # self.Wall = np.vstack([objj.W for objj in self.obj_list])

        # relation
        self.relationHandle.update_prepare()
        self.update_step()

        # action
        for acti in self.action_list:  # type: interactionClass._baseAction
            acti.update_prepare()
        self.check_self()
        if showInfo:
            self.print_info()
        return True

    def update_step(self):
        self.relationHandle.update_relation()
        self.relationHandle.update_neighbor()
        self.relationHandle.check_self()
        return True

    def update_UWall(self, F):
        self.update_step()
        F.zeroEntries()
        # spf.petscInfo(self.logger, F.getArray())
        # print(F.getArray())
        for action in self.action_list:
            action.update_action(F)
            # F.assemble()
        F.assemble()
        # spf.petscInfo(self.logger, F.getArray())
        return True

    def check_self(self, **kwargs):
        # todo: check all parameters.

        err_msg = 'Length must be limited'
        #assert np.isfinite(self.length), err_msg % 'length'

        err_msg = 'Dimension must be 2 or 3 dimensions'
        assert self.dimension in (2, 3), err_msg % 'dimension'

        err_msg = '**kwargs must be limited'
       # assert np.isfinite(self.length), err_msg % '**kwargs'



        for obji in self.obj_list:  # type: particleClass._baseParticle
            obji.check_self()

        for acti in self.action_list:  # type: interactionClass._baseAction
            acti.check_self()

        self.relationHandle.check_self()
        return True

    def update_self(self, t1, t0 = 0, max_it = 10 ** 9, eval_dt = 0.001, pick_prepare = True):
        spf.petscInfo(self.logger, ' ')
        spf.petscInfo(self.logger, 'Solve, start time: %s' % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        self._update_start_time = datetime.now()
        (rtol, atol) = self.update_order
        update_fun = self.update_fun
        tqdm_fun = self.tqdm_fun
        self.t0 = t0
        self.t1 = t1
        self.eval_dt = eval_dt
        self.max_it = max_it
        self.percentage = 0
        self.update_prepare()
        if self.rank0:
            self.tqdm = tqdm_fun(total = 100, desc = '  %s' % self.name)

        # do simulation
        y0 = self._get_y0()
        y = PETSc.Vec().createWithArray(y0, comm = self.comm)
        f = y.duplicate()
        # print(f)
        # print(1111)
        ts = PETSc.TS().create(comm = self.comm)
        ts.setProblemType(ts.ProblemType.NONLINEAR)
        ts.setType(ts.Type.RK)
        ts.setRKType(update_fun)
        ts.setRHSFunction(self._rhsfunction, f)
        ts.setTime(t0)
        ts.setMaxTime(t1)
        ts.setMaxSteps(max_it)
        ts.setTimeStep(eval_dt)
        ts.setMonitor(self._monitor)
        ts.setPostStep(self._postfunction)
        ts.setExactFinalTime(PETSc.TS.ExactFinalTime.MATCHSTEP)
        # ts.setExactFinalTime(PETSc.TS.ExactFinalTime.INTERPOLATE)
        ts.setFromOptions()
        ts.setSolution(y)
        ts.setTolerances(rtol, atol)
        ts.setUp()
        # self._do_store_data(ts, 0, 0, y)
        ts.solve(y)

        # finish simulation
        self.update_finish(ts)
        if pick_prepare:
            self.pick_prepare()
        return True

    @abc.abstractmethod
    def update_position(self, **kwargs):
        return

    @abc.abstractmethod
    def update_velocity(self, **kwargs):
        return

    def update_hist(self, **kwargs):
        for obji in self.obj_list:
            obji.do_store_data()
        return True

    @abc.abstractmethod
    def _get_y0(self, **kwargs):
        return

    @abc.abstractmethod
    def _rhsfunction(self, ts, t, Y, F):
        return

    def _do_store_data(self, ts, i, t, Y):
        if (t <= self.max_it) and self.do_save:
            dt = ts.getTimeStep()
            if self.rank0:
                self.t_hist.append(t)
                self.dt_hist.append(dt)
            self.update_hist()
            return True
        else:
            return False

    def _monitor(self, ts, i, t, Y):
        # i = ts.getStepNumber()  # number of steps completed so far.
        # t = ts.getTime()  # the current time.
        # Y = ts.getSolution()  # Returns the solution at the present timestep.
        save_every = self._save_every
        # print(ts.getTimeStep())
        if not i % save_every:
            percentage = np.clip((t - self._t0) / (self._t1 - self._t0) * 100, 0, 100)
            dp = int(percentage - self.percentage)
            if (dp >= 1) and self.rank0:
                self.tqdm.update(dp)
                self.percentage = self.percentage + dp
            self._do_store_data(ts, i, t, Y)
        return True

    def _postfunction(self, ts):
        return True

    def update_finish(self, ts):
        if self.rank0:
            self.tqdm.update(100 - self.percentage)
            self.tqdm.close()
        time.sleep(0.1)
        spf.petscInfo(self.logger, 'Solve, finish time: %s' % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self._update_stop_time = datetime.now()
        spf.petscInfo(self.logger, 'Solve, usage time: %s' % str(self._update_stop_time - self._update_start_time))
        spf.petscInfo(self.logger, ' ')
        return True

    def pick_prepare(self):
        if self.rank0:
            self._t_hist = np.hstack(self.t_hist)
            self._dt_hist = np.hstack(self.dt_hist)
        for obji in self.obj_list:  # type: particleClass._baseParticle
            obji.update_finish()
        for acti in self.action_list:  # type: interactionClass._baseAction
            acti.update_finish()
        self.relationHandle.check_self()
        return True

    def _destroy_problem(self):
        if self.rank0:
            self._tqdm = None
        return True

    def destroy_self(self, **kwargs):
        self._destroy_problem()
        super().destroy_self(**kwargs)
        for obji in self.obj_list:  # type: particleClass._baseParticle
            obji.destroy_self()
        for acti in self.action_list:  # type: interactionClass._baseAction
            acti.destroy_self()
        self.relationHandle.destroy_self(**kwargs)
        spf.petscInfo(self.logger, 'Destroy problem: %s' % str(self))
        return True

    def _empty_problem(self):
        self._t_hist = np.nan
        self._dt_hist = np.nan
        return True

    def empty_hist(self, **kwargs):
        self._empty_problem()
        for obji in self.obj_list:  # type: particleClass._baseParticle
            obji.empty_hist()
        for acti in self.action_list:  # type: interactionClass._baseAction
            acti.empty_hist()
        self.relationHandle.empty_hist()
        spf.petscInfo(self.logger, 'Empty problem hist: %s' % str(self))
        return True

    def pick_myself(self, **kwargs):
        self.destroy_self()

        # dbg
        # print('dbg')
        # self._obj_list = None
        # self._action_list = None
        # self._relationHandle = None
        comm = PETSc.COMM_WORLD.tompi4py()
        rank = comm.Get_rank()
        if rank == 0:
            with open(self.pickle_name, 'wb') as handle:
                pickle.dump(self, handle, protocol = 4)
        spf.petscInfo(self.logger, 'Pick problem: %s ' % self.pickle_name)
        return True

    def hdf5_pick(self, **kwargs):
        comm = PETSc.COMM_WORLD.tompi4py()
        rank = comm.Get_rank()
        if rank == 0:
            # tsize = self.t_hist.size
            hdf5_kwargs = self.hdf5_kwargs
            with h5py.File(self.hdf5_name, 'w') as handle:
                prb_hist = handle.create_group(self.name)
                prb_hist.create_dataset('t_hist', data = self.t_hist, **hdf5_kwargs)
                prb_hist.create_dataset('dt_hist', data = self.dt_hist, **hdf5_kwargs)
                for obji in self.obj_list:  # type: particleClass._baseParticle
                    obji.hdf5_pick(handle, **kwargs)
        spf.petscInfo(self.logger, 'Pick HDF5 file: %s ' % self.hdf5_name)
        return True

    def hdf5_load(self, hdf5_name = None, showInfo = False, **kwargs):
        comm = PETSc.COMM_WORLD.tompi4py()
        rank = comm.Get_rank()

        if showInfo:
            spf.petscInfo(self.logger, 'Load problem: %s ' % self.hdf5_name)

        hdf5_name = self.hdf5_name if hdf5_name is None else hdf5_name
        if rank == 0:
            with h5py.File(hdf5_name, 'r') as handle:
                prb_hist = handle[self.name]
                self._t_hist = prb_hist['t_hist'][:]
                self._dt_hist = prb_hist['dt_hist'][:]
                for obji in self.obj_list:  # type: # particleClass._baseParticle
                    obji.hdf5_load(handle, **kwargs)

        for obji in self.obj_list:  # type: # particleClass._baseParticle
            obji.father = self
        self.relationHandle.father = self
        for act in self.action_list:
            act.father = self
        self.update_prepare(showInfo = showInfo)

        if showInfo:
            spf.petscInfo(self.logger, ' ')
            spf.petscInfo(self.logger, 'Load finish')
        return True

    def print_self_info(self):
        spf.petscInfo(self.logger, '  rotational noise: %f, translational noise: %f' %
                      (self.rot_noise, self.trs_noise))

    def print_info(self):
        # OptDB = PETSc.Options()
        spf.petscInfo(self.logger, ' ')
        spf.petscInfo(self.logger, 'Information about %s (%s): ' % (str(self), self.type,))
        spf.petscInfo(self.logger, '  This is a %d dimensional problem, contain %d objects. ' %
                      (self.dimension, self.n_obj))
        spf.petscInfo(self.logger, '  update function: %s, update order: %s, max loop: %d' %
                      (self.update_fun, self.update_order, self.max_it))
        spf.petscInfo(self.logger, '  t0=%f, t1=%f, dt=%f' %
                      (self.t0, self.t1, self.eval_dt))
        spf.petscInfo(self.logger, '  save log file to %s ' % self.log_name)
        spf.petscInfo(self.logger, '  save pickle file to %s ' % self.pickle_name)
        self.print_self_info()

        for acti in self.action_list:  # type: interactionClass._baseAction
            acti.print_info()
        self.relationHandle.print_info()
        return True

    # def dbg_t_hist(self, t_hist):
    #     self._t_hist = t_hist
    #     return True


class _base2DProblem(_baseProblem):
    def __init__(self, name = '...', **kwargs):
        super().__init__(name, **kwargs)
        self._Phiall = np.nan
        self._dimension = 2  # 2 for 2D
        self._action_list = uniqueList(acceptType = interactionClass._baseAction2D)  # contain rotational interactions

    @property
    def Phiall(self):
        return self._Phiall

    @Phiall.setter
    def Phiall(self, Phiall):
        self._Phiall = Phiall

    def _check_add_obj(self, obj):
        super()._check_add_obj(obj)
        err_msg = 'wrong object type'
        assert isinstance(obj, particleClass.particle2D), err_msg
        return True

    def update_prepare(self, showInfo = True):
        self.Phiall = np.vstack([objj.phi for objj in self.obj_list])
        super().update_prepare(showInfo = showInfo)
        return True

    def update_position(self, **kwargs):
        obji: particleClass.particle2D
        Xi: np.ndarray
        phii: np.ndarray
        for obji, Xi, phii in zip(self.obj_list, self.Xall, self.Phiall):
            obji.update_position(Xi, phii)
        return True

    def update_velocity(self, **kwargs):
        obji: particleClass.particle2D
        Uall: np.ndarray
        Wall: np.ndarray
        for obji, Ui, Wi in zip(self.obj_list, self.Uall, self.Wall):
            obji.update_velocity(Ui, Wi)
        return True

    def _get_y0(self, **kwargs):
        X_all, phi_all = [], []
        for obji in self.obj_list:
            X_all.append(obji.X)
            phi_all.append(obji.phi)
        y0 = np.hstack([np.hstack(X_all), np.hstack(phi_all)])
        return y0

    def Y2Xphi(self, Y):
        y = self.vec_scatter(Y, destroy = False)
        nobj = self.n_obj
        dim = self.dimension
        X_size = dim * nobj
        X_all = y[0:X_size]
        phi_all = y[X_size:]
        return X_all, phi_all

    def _rhsfunction(self, ts, t, Y, F):
        # structure:
        #   Y = [X_all, phi_all]
        #   F = [U_all, W_all]
        X_all, phi_all = self.Y2Xphi(Y)
        self.Xall, self.Phiall = X_all.reshape((-1, self.dimension)), phi_all
        self.update_position()
        self.update_UWall(F)
        tF = self.vec_scatter(F)
        self.Uall = tF[:self.dimension * self.n_obj].reshape((-1, self.dimension))
        self.Wall = tF[self.dimension * self.n_obj:]
        self.update_velocity()
        # F.assemble()
        # spf.petscInfo(self.logger, ' ')
        # spf.petscInfo(self.logger, 'dbg', t)
        # spf.petscInfo(self.logger, '%+.10f, %+.10f, %+.10f, %+.10f, %+.10f, %+.10f, ' % (
        #     Y.getArray()[0], Y.getArray()[1], Y.getArray()[2],
        #     Y.getArray()[3], Y.getArray()[4], Y.getArray()[5], ))
        # spf.petscInfo(self.logger, '%+.10f, %+.10f, %+.10f, %+.10f, %+.10f, %+.10f, ' % (
        #     F.getArray()[0], F.getArray()[1], F.getArray()[2],
        #     F.getArray()[3], F.getArray()[4], F.getArray()[5], ))
        return True

    def show_particle_location(self):
        if self.rank0:
            figsize, dpi = np.array((1, 1)) * 3, 200

            fig, axi = plt.subplots(1, 1, figsize = figsize, dpi = dpi, constrained_layout = True)
            fig.patch.set_facecolor('white')
            axi.plot(self.Xall[:, 0], self.Xall[:, 1], '.')
            plt.show()
        return True

    def show_particle_directon(self):
        if self.rank0:
            figsize, dpi = np.array((1, 1)) * 3, 200
            fct = 0.2

            fig, axi = plt.subplots(1, 1, figsize = figsize, dpi = dpi, constrained_layout = True)
            fig.patch.set_facecolor('white')
            axi.quiver(self.Xall[:, 0], self.Xall[:, 1],
                       fct * np.cos(self.Phiall), fct * np.sin(self.Phiall))
            plt.show()
        return True


class finiteDipole2DProblem(_base2DProblem):
    def _check_add_obj(self, obj):
        super()._check_add_obj(obj)
        err_msg = 'wrong object type'
        assert isinstance(obj, particleClass.finiteDipole2D), err_msg
        return True


class limFiniteDipole2DProblem(_base2DProblem):
    def _check_add_obj(self, obj):
        super()._check_add_obj(obj)
        err_msg = 'wrong object type'
        assert isinstance(obj, particleClass.limFiniteDipole2D), err_msg
        return True


class behavior2DProblem(_base2DProblem):
    def __init__(self, name = '...', **kwargs):
        super().__init__(name, **kwargs)
        self._attract = np.nan  # attract intensity
        self._align = np.nan  # align intensity
        self._viewRange = np.ones(1) * np.pi  # how large the camera can view
        self._lightDecayFct = 1  # how light strength decay in water, S = S0 * exp(-lightDecayFct * rho)

    @property
    def attract(self):
        return self._attract

    @attract.setter
    def attract(self, attract):
        self._attract = attract

    @property
    def align(self):
        return self._align

    @align.setter
    def align(self, align):
        self._align = align

    @property
    def viewRange(self):
        return self._viewRange

    @viewRange.setter
    def viewRange(self, viewRange):
        err_msg = 'viewRange is a scale. '
        assert viewRange.size == 1, err_msg
        assert -np.pi <= viewRange <= np.pi
        self._viewRange = viewRange

    @property
    def lightDecayFct(self):
        return self._lightDecayFct

    @lightDecayFct.setter
    def lightDecayFct(self, lightDecayFct):
        err_msg = 'lightDecayFct is a positive factor. '
        assert lightDecayFct > 0, err_msg
        self._lightDecayFct = lightDecayFct

    def add_obj(self, obj: "particleClass.particle2D"):
        super().add_obj(obj)
        obj.attract = self.attract
        obj.align = self.align
        obj.viewRange = self.viewRange
        return True

    def print_self_info(self):
        super().print_self_info()
        spf.petscInfo(self.logger, '  align: %f, attract: %f, viewRange: %f, ' %
                      (self.align, self.attract, self.viewRange))


class behaviorFiniteDipole2DProblem(behavior2DProblem, finiteDipole2DProblem):
    def _nothing(self):
        pass


class actLimFiniteDipole2DProblem(behavior2DProblem, limFiniteDipole2DProblem):
    def _nothing(self):
        pass


class periodic2DProblem(_base2DProblem):
    def __init__(self, name = '...', Xrange = 1, **kwargs):
        super().__init__(name, **kwargs)
        self._Xrange = Xrange
        self._halfXrange = Xrange / 2

    @property
    def Xrange(self):
        return self._Xrange

    @property
    def halfXrange(self):
        return self._halfXrange

    def _postfunction(self, ts):
        super()._postfunction(ts)
        Y = ts.getSolution()
        X_all, phi_all = self.Y2Xphi(Y)
        # print('dbg')
        # t1 = X_all.reshape((-1, 2)).ravel()
        # # print(X_all)
        # # print(t1)
        # print(id(X_all), id(t1), np.allclose(X_all, t1))
        X_all = spf.warpMinMax(X_all, -self.Xrange / 2, self.Xrange / 2)
        self.Xall, self.Phiall = X_all.reshape((-1, 2)), phi_all
        self.update_position()
        Y[:] = np.hstack((self.Xall.ravel(), self.Phiall))
        Y.assemble()
        return True


class actPeriodic2DProblem(periodic2DProblem, behavior2DProblem):
    # class actPeriodic2DProblem(behavior2DProblem):
    def _nothing(self):
        pass


class Ackermann2DProblem(_base2DProblem):
    def __init__(self, name = '...', **kwargs):
        super().__init__(name, **kwargs)
        self._Phi_steer_all = np.nan

    @property
    def Phi_steer_all(self):
        return self._Phi_steer_all

    @Phi_steer_all.setter
    def Phi_steer_all(self, Phi_steer_all):
        self._Phi_steer_all = Phi_steer_all

    def _check_add_obj(self, obj):
        super()._check_add_obj(obj)
        err_msg = 'wrong object type'
        assert isinstance(obj, particleClass.ackermann2D), err_msg
        return True

    def update_prepare(self, showInfo = True):
        self.Phi_steer_all = np.vstack([objj.phi_steer for objj in self.obj_list])
        super().update_prepare(showInfo = showInfo)
        return True

    def update_position(self, **kwargs):
        obji: particleClass.ackermann2D
        Xi: np.ndarray
        phii: np.ndarray
        for obji, Xi, phii, phi_steeri in zip(self.obj_list, self.Xall, self.Phiall, self.Phi_steer_all):
            obji.update_position(Xi, phii, phi_steer = phi_steeri)
        return True

    def _get_y0(self, **kwargs):
        X_all, phi_all, phi_steer_all = [], [], []
        for obji in self.obj_list:
            X_all.append(obji.X)
            phi_all.append(obji.phi)
            phi_steer_all.append(obji.phi_steer)
        y0 = np.hstack([np.hstack(X_all), np.hstack(phi_all), np.hstack(phi_steer_all)])
        return y0

    def Y2Xphi(self, Y):
        y = self.vec_scatter(Y, destroy = False)
        nobj = self.n_obj
        dim = self.dimension
        X_size = dim * nobj
        X_all = y[0:X_size]
        phi_all = y[X_size:X_size + nobj]
        phi_steer_all = y[X_size + nobj:]
        return X_all, phi_all, phi_steer_all

    def _rhsfunction(self, ts, t, Y, F):
        # structure:
        #   Y = [X_all, phi_all]
        #   F = [U_all, W_all]
        X_all, phi_all, phi_steer_all = self.Y2Xphi(Y)
        self.Xall = X_all.reshape((-1, self.dimension))
        self.Phiall = phi_all
        self.Phi_steer_all = phi_steer_all
        self.update_position()
        self.update_UWall(F)
        tF = self.vec_scatter(F)
        self.Uall = tF[:self.dimension * self.n_obj].reshape((-1, self.dimension))
        self.Wall = tF[self.dimension * self.n_obj:]
        self.update_velocity()
        return True
