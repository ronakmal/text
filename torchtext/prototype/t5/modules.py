# /* Portions Copyright (c) Meta Platforms, Inc. and affiliates.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Original code is taken from
# https://github.com/huggingface/transformers/blob/main/src/transformers/models/t5/modeling_t5.py
# */

import math

import torch
from torch import Tensor


# NOTE: modified from https://github.com/huggingface/transformers/blob/main/src/transformers/models/t5/modeling_t5.py
def _compute_bias(
    query_length: int,
    key_length: int,
    relative_attention_bias: Tensor,
    relative_attention_num_buckets: int = 32,
    relative_attention_max_distance: int = 128,
    bidirectional: bool = True,
    device=None,
):
    """Compute binned relative position bias"""
    if device is None:
        device = relative_attention_bias.weight.device
    context_position = torch.arange(query_length, dtype=torch.long, device=device)[:, None]
    memory_position = torch.arange(key_length, dtype=torch.long, device=device)[None, :]
    relative_position = memory_position - context_position  # shape (query_length, key_length)
    relative_position_bucket = self._relative_position_bucket(
        relative_position,  # shape (query_length, key_length)
        bidirectional=bidirectional,
        num_buckets=relative_attention_num_buckets,
        max_distance=relative_attention_max_distance,
    )
    values = relative_attention_bias(relative_position_bucket)  # shape (query_length, key_length, num_heads)
    values = values.permute([2, 0, 1]).unsqueeze(0)  # shape (1, num_heads, query_length, key_length)
    return values


# NOTE: taken from https://github.com/huggingface/transformers/blob/main/src/transformers/models/t5/modeling_t5.py
def _relative_position_bucket(
    relative_position: Tensor, bidirectional: bool = True, num_buckets: int = 32, max_distance: int = 128
):
    """
    Adapted from Mesh Tensorflow:
    https://github.com/tensorflow/mesh/blob/0cb87fe07da627bf0b7e60475d59f95ed6b5be3d/mesh_tensorflow/transformer/transformer_layers.py#L593
    Translate relative position to a bucket number for relative attention. The relative position is defined as
    memory_position - query_position, i.e. the distance in tokens from the attending position to the attended-to
    position. If bidirectional=False, then positive relative positions are invalid. We use smaller buckets for
    small absolute relative_position and larger buckets for larger absolute relative_positions. All relative
    positions >=max_distance map to the same bucket. All relative positions <=-max_distance map to the same bucket.
    This should allow for more graceful generalization to longer sequences than the model has been trained on
    Args:
        relative_position: an int32 Tensor
        bidirectional: a boolean - whether the attention is bidirectional
        num_buckets: an integer
        max_distance: an integer
    Returns:
        a Tensor with the same shape as relative_position, containing int32 values in the range [0, num_buckets)
    """
    relative_buckets = 0
    if bidirectional:
        num_buckets //= 2
        relative_buckets += (relative_position > 0).to(torch.long) * num_buckets
        relative_position = torch.abs(relative_position)
    else:
        relative_position = -torch.min(relative_position, torch.zeros_like(relative_position))
    # now relative_position is in the range [0, inf)

    # half of the buckets are for exact increments in positions
    max_exact = num_buckets // 2
    is_small = relative_position < max_exact

    # The other half of the buckets are for logarithmically bigger bins in positions up to max_distance
    relative_position_if_large = max_exact + (
        torch.log(relative_position.float() / max_exact)
        / math.log(max_distance / max_exact)
        * (num_buckets - max_exact)
    ).to(torch.long)
    relative_position_if_large = torch.min(
        relative_position_if_large, torch.full_like(relative_position_if_large, num_buckets - 1)
    )

    relative_buckets += torch.where(is_small, relative_position, relative_position_if_large)
    return relative_buckets
