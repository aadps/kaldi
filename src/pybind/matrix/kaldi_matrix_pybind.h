// pybind/matrix/kaldi_matrix_pybind.h

// Copyright 2019   Daniel Povey
//           2019   Dongji Gao
//           2019   Mobvoi AI Lab, Beijing, China (author: Fangjun Kuang)

// See ../../../COPYING for clarification regarding multiple authors
//
// Licensed under the Apache License, Version 2.0 (the "License");
//
//  http://www.apache.org/licenses/LICENSE-2.0
//
// THIS CODE IS PROVIDED *AS IS* BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
// KIND, EITHER EXPRESS OR IMPLIED, INCLUDING WITHOUT LIMITATION ANY IMPLIED
// WARRANTIES OR CONDITIONS OF TITLE, FITNESS FOR A PARTICULAR PURPOSE,
// MERCHANTABLITY OR NON-INFRINGEMENT.
// See the Apache 2 License for the specific language governing permissions and
// limitations under the License.

#ifndef KALDI_PYBIND_MATRIX_KALDI_MATRIX_PYBIND_H_
#define KALDI_PYBIND_MATRIX_KALDI_MATRIX_PYBIND_H_

#include "pybind/kaldi_pybind.h"

void pybind_kaldi_matrix(py::module& m);

#endif  // KALDI_PYBIND_MATRIX_KALDI_MATRIX_PYBIND_H_
