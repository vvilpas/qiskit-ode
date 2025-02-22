# -*- coding: utf-8 -*-

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

"""
==========================================
Qiskit ODE (:mod:`qiskit_ode`)
==========================================

.. currentmodule:: qiskit_ode

qiskit extension module for solving ordinary differential equations.
"""
from .version import __version__

from .solve import solve_ode, solve_lmde

from . import models
from . import signals
from . import converters
from . import dispatch
