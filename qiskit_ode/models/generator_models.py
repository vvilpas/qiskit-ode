# This code is part of Qiskit.
#
# (C) Copyright IBM 2020.
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.
# pylint: disable=invalid-name

"""
Generator models module.
"""

from abc import ABC, abstractmethod
from typing import Callable, Union, List, Optional
from copy import deepcopy
import numpy as np

from qiskit import QiskitError
from qiskit.quantum_info.operators import Operator
from qiskit_ode import dispatch
from qiskit_ode.dispatch import Array
from qiskit_ode.type_utils import to_array
from qiskit_ode.signals import VectorSignal, BaseSignal
from .frame import BaseFrame, Frame


class BaseGeneratorModel(ABC):
    r"""BaseGeneratorModel is an abstract interface for a time-dependent operator
    :math:`G(t)`, with functionality of relevance for differential
    equations of the form :math:`\dot{y}(t) = G(t)y(t)`.

    The core functionality is evaluation of :math:`G(t)` and the products
    :math:`AG(t)` and :math:`G(t)A`, for operators :math:`A` of suitable
    shape.

    Additionally, this abstract class requires implementation of 3 properties
    to facilitate the use of this object in solving differential equations:
        - A "drift", which is meant to return the "time-independent" part of
          :math:`G(t)`
        - A "frame", here specified as a :class:`BaseFrame` object, which
          represents an anti-Hermitian operator :math:`F`, specifying
          the transformation :math:`G(t) \mapsto G'(t) = e^{-tF}G(t)e^{tF} - F`.

          If a frame is set, the evaluation functions are modified to work
          with G'(t). Furthermore, all evaluation functions have the option
          to return the results in a basis in which :math:`F` is diagonalized,
          to save on the cost of computing :math:`e^{\pm tF}`.
        - A `cutoff_freq`: a cutoff frequency for further modifying the
          evaluation of :math:`G'(t)` to remove terms above a given frequency.
          In this abstract class the exact meaning of this is left unspecified;
          it is left to concrete implementations to define this.
    """

    @property
    @abstractmethod
    def frame(self) -> BaseFrame:
        """Get the frame."""
        pass

    @frame.setter
    @abstractmethod
    def frame(self, frame: BaseFrame):
        """Set the frame."""
        pass

    @property
    @abstractmethod
    def cutoff_freq(self) -> float:
        """Get cutoff frequency."""
        pass

    @cutoff_freq.setter
    @abstractmethod
    def cutoff_freq(self, cutoff_freq: float):
        """Set cutoff frequency."""
        pass

    @abstractmethod
    def evaluate(self, time: float, in_frame_basis: bool = False) -> Array:
        """Evaluate the model at a given time."""
        pass

    def lmult(self, time: float, y: Array, in_frame_basis: bool = False) -> Array:
        r"""Return the product evaluate(t) @ y. Default implementation is to
        call evaluate then multiply.

        Args:
            time: Time at which to create the generator.
            y: operator or vector to apply the model to.
            in_frame_basis: whether to evaluate in the frame basis

        Returns:
            Array: the product
        """
        return np.dot(self.evaluate(time, in_frame_basis), y)

    def rmult(self, time: float, y: Array, in_frame_basis: bool = False) -> Array:
        r"""Return the product y @ evaluate(t). Default implementation is to
        call evaluate then multiply.

        Args:
            time: Time at which to create the generator.
            y: operator or vector to apply the model to.
            in_frame_basis: whether to evaluate in the frame basis

        Returns:
            Array: the product
        """
        return np.dot(y, self.evaluate(time, in_frame_basis))

    @property
    @abstractmethod
    def drift(self) -> Array:
        """Evaluate the constant part of the model."""
        pass

    def copy(self):
        """Return a copy of self."""
        return deepcopy(self)

    def __call__(self, t: float, y: Optional[Array] = None, in_frame_basis: Optional[bool] = False):
        """Evaluate generator RHS functions. If ``y is None``,
        evaluates the model, and otherwise evaluates ``G(t) @ y``.

        Args:
            t: Time.
            y: Optional state.
            in_frame_basis: Whether or not to evaluate in the frame basis.

        Returns:
            Array: Either the evaluated model or the RHS for the given y
        """

        if y is None:
            return self.evaluate(t, in_frame_basis=in_frame_basis)

        return self.lmult(t, y, in_frame_basis=in_frame_basis)


class CallableGenerator(BaseGeneratorModel):
    """Generator specified as a callable"""

    def __init__(
        self,
        generator: Callable,
        frame: Optional[Union[Operator, Array, BaseFrame]] = None,
        drift: Optional[Union[Operator, Array]] = None,
    ):

        self._generator = dispatch.wrap(generator)
        self.frame = frame
        self._drift = drift

    @property
    def frame(self) -> Frame:
        """Return the frame."""
        return self._frame

    @frame.setter
    def frame(self, frame: Union[Operator, Array, Frame]):
        """Set the frame; either an already instantiated :class:`Frame` object
        a valid argument for the constructor of :class:`Frame`, or `None`.
        """
        self._frame = Frame(frame)

    @property
    def cutoff_freq(self) -> float:
        """Return the cutoff frequency."""
        return None

    @cutoff_freq.setter
    def cutoff_freq(self, cutoff_freq: float):
        """Cutoff frequency not supported for generic."""
        if cutoff_freq is not None:
            raise QiskitError("""Cutoff frequency is not supported for function-based generator.""")

    @property
    def drift(self) -> Array:
        return self._drift

    def evaluate(self, time: float, in_frame_basis: bool = False) -> Array:
        """Evaluate the model in array format.

        Args:
            time: Time to evaluate the model
            in_frame_basis: Whether to evaluate in the basis in which the frame
                            operator is diagonal

        Returns:
            Array: the evaluated model

        Raises:
            QiskitError: If model cannot be evaluated.
        """

        # evaluate generator and map it into the frame
        gen = self._generator(time)
        return self.frame.generator_into_frame(
            time, gen, operator_in_frame_basis=False, return_in_frame_basis=in_frame_basis
        )


class GeneratorModel(BaseGeneratorModel):
    r"""GeneratorModel is a concrete instance of BaseGeneratorModel, where the
    operator :math:`G(t)` is explicitly constructed as:

    .. math::

        G(t) = \sum_{i=0}^{k-1} s_i(t) G_i,

    where the :math:`G_i` are matrices (represented by :class:`Operator`
    objects), and the :math:`s_i(t)` given by signals represented by a
    :class:`VectorSignal` object, or a list of :class:`Signal` objects.

    The signals in the model can be specified at instantiation, or afterwards
    by setting the ``signals`` attribute, by giving a
    list of :class:`Signal` objects or a :class:`VectorSignal`.

    For specifying a frame, this object works with the concrete
    :class:`Frame`, a subclass of :class:`BaseFrame`.

    To do:
        insert mathematical description of frame/cutoff_freq handling
    """

    def __init__(
        self,
        operators: Array,
        signals: Optional[Union[VectorSignal, List[BaseSignal]]] = None,
        frame: Optional[Union[Operator, Array, BaseFrame]] = None,
        cutoff_freq: Optional[float] = None,
    ):
        """Initialize.

        Args:
            operators: A rank-3 Array of operator components.
            signals: Specifiable as either a VectorSignal, a list of
                     Signal objects, or as the inputs to signal_mapping.
                     GeneratorModel can be instantiated without specifying
                     signals, but it can not perform any actions without them.
            frame: Rotating frame operator. If specified with a 1d
                            array, it is interpreted as the diagonal of a
                            diagonal matrix.
            cutoff_freq: Frequency cutoff when evaluating the model.
        """
        self.operators = to_array(operators)

        self._cutoff_freq = cutoff_freq

        # initialize signal-related attributes
        self._signal_params = None
        self._signals = None
        self.signals = signals

        # set frame
        self.frame = frame

        # initialize internal operator representation in the frame basis
        self.__ops_in_fb_w_cutoff = None
        self.__ops_in_fb_w_conj_cutoff = None

    @property
    def signals(self) -> VectorSignal:
        """Return the signals in the model."""
        return self._signals

    @signals.setter
    def signals(self, signals: Union[VectorSignal, List[BaseSignal]]):
        """Set the signals."""

        if signals is None:
            self._signal_params = None
            self._signals = None
        else:
            # if signals is a list, instantiate a VectorSignal
            if isinstance(signals, list):
                signals = VectorSignal.from_signal_list(signals)

            # if it isn't a VectorSignal by now, raise an error
            if not isinstance(signals, VectorSignal):
                raise QiskitError("signals specified in unaccepted format.")

            # verify signal length is same as operators
            if len(signals.carrier_freqs) != len(self.operators):
                raise QiskitError(
                    """signals needs to have the same length as
                                    operators."""
                )

            # internal ops need to be reset if there is a cutoff frequency
            # and carrier_freqs has changed
            if self._signals is not None:
                if (
                    not np.allclose(self._signals.carrier_freqs, signals.carrier_freqs)
                    and self._cutoff_freq is not None
                ):
                    self._reset_internal_ops()

            self._signals = signals

    @property
    def frame(self) -> Frame:
        """Return the frame."""
        return self._frame

    @frame.setter
    def frame(self, frame: Union[Operator, Array, Frame]):
        """Set the frame; either an already instantiated :class:`Frame` object
        a valid argument for the constructor of :class:`Frame`, or `None`.
        """

        self._frame = Frame(frame)

        self._reset_internal_ops()

    @property
    def cutoff_freq(self) -> float:
        """Return the cutoff frequency."""
        return self._cutoff_freq

    @cutoff_freq.setter
    def cutoff_freq(self, cutoff_freq: float):
        """Set the cutoff frequency."""
        if cutoff_freq != self._cutoff_freq:
            self._cutoff_freq = cutoff_freq
            self._reset_internal_ops()

    def evaluate(self, time: float, in_frame_basis: bool = False) -> Array:
        """Evaluate the model in array format.

        Args:
            time: Time to evaluate the model
            in_frame_basis: Whether to evaluate in the basis in which the frame
                            operator is diagonal

        Returns:
            Array: the evaluated model

        Raises:
            QiskitError: If model cannot be evaluated.
        """

        if self._signals is None:
            raise QiskitError("""GeneratorModel cannot be evaluated without signals.""")

        sig_vals = self._signals.value(time)

        # evaluate the linear combination in the frame basis with cutoffs,
        # then map into the frame
        op_combo = self._evaluate_in_frame_basis_with_cutoffs(sig_vals)
        return self.frame.generator_into_frame(
            time, op_combo, operator_in_frame_basis=True, return_in_frame_basis=in_frame_basis
        )

    @property
    def drift(self) -> Array:
        """Return the part of the model with only Constant coefficients as a
        numpy array.
        """

        # for now if the frame operator is not None raise an error
        if self.frame.frame_operator is not None:
            raise QiskitError(
                """The drift is currently ill-defined if
                               frame_operator is not None."""
            )

        drift_sig_vals = self._signals.drift_array

        return self._evaluate_in_frame_basis_with_cutoffs(drift_sig_vals)

    def _construct_ops_in_fb_w_cutoff(self):
        """Construct versions of operators in frame basis with cutoffs
        and conjugate cutoffs. To be used in conjunction with
        operators_into_frame_basis_with_cutoff to compute the operator in the
        frame basis with frequency cutoffs applied.
        """
        carrier_freqs = None
        if self._signals.carrier_freqs is None:
            carrier_freqs = np.zeros(len(self.operators))
        else:
            carrier_freqs = self._signals.carrier_freqs

        (
            self.__ops_in_fb_w_cutoff,
            self.__ops_in_fb_w_conj_cutoff,
        ) = self.frame.operators_into_frame_basis_with_cutoff(
            self.operators, self.cutoff_freq, carrier_freqs
        )

    def _reset_internal_ops(self):
        """Helper function to be used by various setters whose value changes
        require reconstruction of the internal operators.
        """
        self.__ops_in_fb_w_cutoff = None
        self.__ops_in_fb_w_conj_cutoff = None

    @property
    def _ops_in_fb_w_cutoff(self):
        r"""Internally stored operators in frame basis with cutoffs.
        This corresponds to the :math:`A^+` matrices from
        `Frame.operators_into_frame_basis_with_cutoff`.

        Returns:
            Array: operators in frame basis with cutoff
        """
        if self.__ops_in_fb_w_cutoff is None:
            self._construct_ops_in_fb_w_cutoff()

        return self.__ops_in_fb_w_cutoff

    @property
    def _ops_in_fb_w_conj_cutoff(self):
        """Internally stored operators in frame basis with conjugate cutoffs.
        This corresponds to the :math:`A^-` matrices from
        `Frame.operators_into_frame_basis_with_cutoff`.

        Returns:
            Array: operators in frame basis with conjugate cutoff
        """
        if self.__ops_in_fb_w_conj_cutoff is None:
            self._construct_ops_in_fb_w_cutoff()

        return self.__ops_in_fb_w_conj_cutoff

    def _evaluate_in_frame_basis_with_cutoffs(self, sig_vals: Array):
        """Evaluate the operator in the frame basis with frequency cutoffs.
        The computation here corresponds to that prescribed in
        `Frame.operators_into_frame_basis_with_cutoff`.

        Args:
            sig_vals: Signals evaluated at some time.

        Returns:
            Array: operator model evaluated for a given list of signal values
        """

        return 0.5 * (
            np.tensordot(sig_vals, self._ops_in_fb_w_cutoff, axes=1)
            + np.tensordot(sig_vals.conj(), self._ops_in_fb_w_conj_cutoff, axes=1)
        )
