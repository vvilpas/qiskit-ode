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
Lindblad models module.
"""

from typing import Union, List, Optional
import numpy as np

from qiskit.quantum_info.operators import Operator
from qiskit_ode.signals import VectorSignal, BaseSignal
from qiskit_ode.type_utils import vec_commutator, vec_dissipator, to_array
from .generator_models import GeneratorModel
from .hamiltonian_models import HamiltonianModel


class LindbladModel(GeneratorModel):
    r"""A model of a quantum system in terms of the Lindblad master equation.

    The Lindblad master equation models the evolution of a density matrix according to:

    .. math::
        \dot{\rho}(t) = -i[H(t), \rho(t)] + \mathcal{D}(t)(\rho(t)),

    where :math:`\mathcal{D}(t)` is the dissipator portion of the equation,
    given by

    .. math::
        \mathcal{D}(t)(\rho(t)) = \sum_j \gamma_j(t) L_j \rho L_j^\dagger
                                  - \frac{1}{2} \{L_j^\dagger L_j, \rho\},

    with :math:`[\cdot, \cdot]` and :math:`\{\cdot, \cdot\}` the
    matrix commutator and anti-commutator, respectively. In the above:

        - :math:`H(t)` denotes the Hamiltonian,
        - :math:`L_j` denotes the :math:`j^{th}` noise, or Lindblad,
          operator, and
        - :math:`\gamma_j(t)` denotes the signal corresponding to the
          :math:`j^{th}` Lindblad operator.
    """

    def __init__(
        self,
        hamiltonian_operators: List[Operator],
        hamiltonian_signals: Union[List[BaseSignal], VectorSignal],
        noise_operators: Optional[List[Operator]] = None,
        noise_signals: Optional[Union[List[BaseSignal], VectorSignal]] = None,
    ):
        """Initialize.

        Args:
            hamiltonian_operators: list of operators in Hamiltonian
            hamiltonian_signals: list of signals in the Hamiltonian
            noise_operators: list of noise operators
            noise_signals: list of noise signals

        Raises:
            Exception: if signals incorrectly specified
        """

        # combine operators
        vec_ham_ops = -1j * vec_commutator(to_array(hamiltonian_operators))

        full_operators = None
        if noise_operators is not None:
            vec_diss_ops = vec_dissipator(to_array(noise_operators))
            full_operators = np.append(vec_ham_ops, vec_diss_ops, axis=0)
        else:
            full_operators = vec_ham_ops

        # combine signals
        if isinstance(hamiltonian_signals, list):
            hamiltonian_signals = VectorSignal.from_signal_list(hamiltonian_signals)
        elif not isinstance(hamiltonian_signals, VectorSignal):
            raise Exception(
                """hamiltonian_signals must either be a list of
                             Signals, or a VectorSignal."""
            )

        full_signals = None
        if noise_operators is None:
            full_signals = hamiltonian_signals
        else:
            if noise_signals is None:
                sig_val = np.ones(len(noise_operators), dtype=complex)
                carrier_freqs = np.zeros(len(noise_operators), dtype=float)
                phases = np.zeros(len(noise_operators), dtype=float)
                noise_signals = VectorSignal(
                    envelope=lambda t: sig_val, carrier_freqs=carrier_freqs, phases=phases
                )
            elif isinstance(noise_signals, list):
                noise_signals = VectorSignal.from_signal_list(noise_signals)
            elif not isinstance(noise_signals, VectorSignal):
                raise Exception(
                    """noise_signals must either be a list of
                                 Signals, or a VectorSignal."""
                )

            def full_envelope(t):
                return np.append(hamiltonian_signals.envelope(t), noise_signals.envelope(t))

            full_carrier_freqs = np.append(
                hamiltonian_signals.carrier_freqs, noise_signals.carrier_freqs
            )

            full_carrier_phases = np.append(hamiltonian_signals.phases, noise_signals.phases)

            full_drift_array = np.append(hamiltonian_signals.drift_array, noise_signals.drift_array)

            full_signals = VectorSignal(
                envelope=full_envelope,
                carrier_freqs=full_carrier_freqs,
                phases=full_carrier_phases,
                drift_array=full_drift_array,
            )

        super().__init__(operators=full_operators, signals=full_signals)

    @classmethod
    def from_hamiltonian(
        cls,
        hamiltonian: HamiltonianModel,
        noise_operators: Optional[List[Operator]] = None,
        noise_signals: Optional[Union[List[BaseSignal], VectorSignal]] = None,
    ):
        """Construct from a :class:`HamiltonianModel`.

        Args:
            hamiltonian: the :class:`HamiltonianModel`.
            noise_operators: list of noise operators.
            noise_signals: list of noise signals.

        Returns:
            LindbladModel: Linblad model from parameters.
        """

        return cls(
            hamiltonian_operators=hamiltonian.operators,
            hamiltonian_signals=hamiltonian.signals,
            noise_operators=noise_operators,
            noise_signals=noise_signals,
        )
