import torch
from torch.autograd.function import Function
from torch._thnn import type2backend

from . import _all_functions


class Embedding(Function):

    def __init__(self, padding_idx, max_norm, norm_type, scale_grad_by_freq):
        super(Embedding, self).__init__()
        self.padding_idx = padding_idx
        self.max_norm = max_norm
        self.norm_type = norm_type
        self.scale_grad_by_freq = scale_grad_by_freq
        self._indices = None

    def _renorm(self, indices, weight):
        if indices.dim() == 2:
            indices = indices.view(-1)

        self._backend.LookupTable_renorm(
            self._backend.library_state,
            indices,
            weight,
            self.max_norm,
            self.norm_type
        )

    def forward(self, indices, weight):
        assert indices.dim() <= 2
        assert not self.needs_input_grad[0], "Embedding doesn't " \
            "compute the gradient w.r.t. the indices"
        self._backend = type2backend[type(weight)]
        self._weight_size = weight.size()

        if not indices.is_contiguous():
            self._indices = indices.contiguous()
            indices = self._indices
        else:
            self.save_for_backward(indices)

        if self.max_norm is not None:
            self._renorm(indices, weight)

        output = weight.new()
        if indices.dim() == 1:
            torch.index_select(output, weight, 0, indices)
        else:
            torch.index_select(output, weight, 0, indices.view(-1))
            output = output.view(indices.size(0), indices.size(1), weight.size(1))

        return output

    def backward(self, grad_output):
        if self._indices is not None:
            indices = self._indices
        else:
            indices, = self.saved_tensors

        if indices.dim() == 2:
            indices = indices.view(-1)

        grad_output = grad_output.contiguous()

        if torch.typename(grad_output) == 'torch.cuda.FloatTensor':
            _sorted = torch.cuda.LongTensor()
            _indices = torch.cuda.LongTensor()
            _count = torch.cuda.LongTensor()
        else:
            _count = torch.IntTensor()
            _sorted = _indices = None

        # TODO: sparse updates...
        grad_weight = type(grad_output)(self._weight_size).zero_()
        self._backend.LookupTable_accGradParameters(
            self._backend.library_state,
            indices,
            grad_output,
            grad_weight,
            _count,
            _sorted,
            _indices,
            self.scale_grad_by_freq,
            self.padding_idx,
            1
        )
        return None, grad_weight


_all_functions.append(Embedding)
