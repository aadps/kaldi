#!/usr/bin/env python3

# Copyright 2019-2020 Mobvoi AI Lab, Beijing, China (author: Fangjun Kuang)
# Apache 2.0

import glob
import os

import numpy as np
import torch

from torch.utils.data import DataLoader
from torch.utils.data import Dataset

import kaldi_pybind.nnet3 as nnet3
import kaldi

from common import splice_feats

def get_egs_dataloader(egs_dir_or_scp,
                       egs_left_context,
                       egs_right_context,
                       world_size=None,
                       local_rank=None):
    '''
    world_size and local_rank is for DistributedDataParallel training.
    '''
    dataset = NnetChainExampleDataset(egs_dir_or_scp=egs_dir_or_scp)
    frame_subsampling_factor = 3

    # we have merged egs offline, so batch size is 1
    batch_size = 1

    collate_fn = NnetChainExampleDatasetCollateFunc(
        egs_left_context=egs_left_context,
        egs_right_context=egs_right_context,
        frame_subsampling_factor=frame_subsampling_factor)

    if local_rank != None:
        sampler = torch.utils.data.distributed.DistributedSampler(
            dataset, num_replicas=world_size, rank=local_rank, shuffle=True)
        dataloader = DataLoader(dataset,
                                batch_size=batch_size,
                                collate_fn=collate_fn,
                                sampler=sampler)
    else:
        base_sampler = torch.utils.data.RandomSampler(dataset)
        sampler = torch.utils.data.BatchSampler(
            base_sampler, batch_size, False)
        dataloader = DataLoader(dataset,
                                batch_sampler=sampler,
                                collate_fn=collate_fn)
    return dataloader


def read_nnet_chain_example(rxfilename):
    eg = nnet3.NnetChainExample()
    ki = kaldi.Input()
    is_opened, is_binary = ki.Open(rxfilename, read_header=True)
    if not is_opened:
        raise Exception('Failed to open {}'.format(rxfilename))
    eg.Read(ki.Stream(), is_binary)
    ki.Close()
    return eg


class NnetChainExampleDataset(Dataset):

    def __init__(self, egs_dir_or_scp):
        '''
        If egs_dir_or_scp is a directory, we assume that there exist many cegs.*.scp files
        inside egs_dir_or_scp.
        '''
        if os.path.isdir(egs_dir_or_scp):
            self.scps = glob.glob('{}/cegs.*.scp'.format(egs_dir_or_scp))
        else:
            self.scps = [egs_dir_or_scp]

        assert len(self.scps) > 0
        self.items = list()
        for scp in self.scps:
            with open(scp, 'r') as f:
                for line in f:
                    # line should be: "key rxfilename"
                    split = line.split()
                    assert len(split) == 2
                    self.items.append(split)

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        return self.items[i]

    def __str__(self):
        s = 'num egs scps: {}\n'.format(len(self.scps))
        s = 'num egs: {}\n'.format(len(self.items))
        return s


class NnetChainExampleDatasetCollateFunc:

    def __init__(self, egs_left_context, egs_right_context,
                 frame_subsampling_factor):
        '''
        egs_left_context is from egs/info/left_context
        egs_right_context is from egs/info/right_context
        '''

        assert egs_left_context >= 0
        assert egs_right_context >= 0

        # we currently support either no subsampling or
        # subsampling factor to be 3
        assert frame_subsampling_factor in [1, 3]

        self.egs_left_context = egs_left_context
        self.egs_right_context = egs_right_context
        self.frame_subsampling_factor = frame_subsampling_factor

    def __call__(self, batch):
        '''
        batch is a list of [key, rxfilename]
        returned from `__getitem__()` of `NnetChainExampleDataset`

        Since we combined egs offline, the batch size is usually one.
        '''

        key_list = []

        # contains a list of a 3D array
        # of shape [batch_size, seq_len, feat_dim]
        feature_list = []

        supervision_list = []
        for b in batch:
            key, rxfilename = b
            key_list.append(key)
            eg = read_nnet_chain_example(rxfilename)

            assert len(eg.outputs) == 1
            assert eg.outputs[0].name == 'output'

            supervision = eg.outputs[0].supervision
            supervision_list.append(supervision)

            batch_size = supervision.num_sequences

            frames_per_sequence = (supervision.frames_per_sequence *
                                   self.frame_subsampling_factor) + \
                self.egs_left_context + self.egs_right_context

            assert eg.inputs[0].name == 'input'

            _feats = kaldi.FloatMatrix()
            eg.inputs[0].features.GetMatrix(_feats)
            feats = _feats.numpy()

            if len(eg.inputs) > 1:
                _ivectors = kaldi.FloatMatrix()
                eg.inputs[1].features.GetMatrix(_ivectors)
                ivectors = _ivectors.numpy()

            assert feats.shape[0] == batch_size * frames_per_sequence

            feat_list = []
            for i in range(batch_size):
                start_index = i * frames_per_sequence
                if self.frame_subsampling_factor == 3:
                    shift = np.random.choice([-1, 0, 1], 1)[0]
                    start_index += shift

                end_index = start_index + frames_per_sequence

                start_index += 2  # remove the leftmost frame added for frame shift
                end_index -= 2  # remove the rightmost frame added for frame shift
                feat = feats[start_index:end_index:, :]
                if len(eg.inputs) > 1:
                    repeat_ivector = torch.from_numpy(
                        ivectors[i]).repeat(feat.shape[0], 1)
                    feat = torch.cat(
                        (torch.from_numpy(feat), repeat_ivector), dim=1).numpy()
                feat_list.append(feat)

            batched_feat = np.stack(feat_list, axis=0)
            assert batched_feat.shape[0] == batch_size

            # -4 = -2 -2
            # the first -2 is from extra left/right context
            # the second -2 is from lda feats splicing
            assert batched_feat.shape[1] == frames_per_sequence - 4
            if len(eg.inputs) > 1:
                assert batched_feat.shape[2] == feats.shape[-1] + ivectors.shape[-1]
            else:
                assert batched_feat.shape[2] == feats.shape[-1]

            torch_feat = torch.from_numpy(batched_feat).float()
            feature_list.append(torch_feat)

        return key_list, feature_list, supervision_list


def _test_nnet_chain_example_dataset():
    egs_dir = 'exp/chain_pybind/tdnnivector_delta_sp/merged_egs_chain2'
    dataset = NnetChainExampleDataset(egs_dir_or_scp=egs_dir)
    egs_left_context = 29
    egs_right_context = 29
    frame_subsampling_factor = 3

    collate_fn = NnetChainExampleDatasetCollateFunc(
        egs_left_context=egs_left_context,
        egs_right_context=egs_right_context,
        frame_subsampling_factor=frame_subsampling_factor)

    # FIXME(fangjun): num_workers > 0 causes errors!
    # How to reproduce the error?
    # 1. add a destructor to `struct Supervision` in `chain/chain-superversion.h`
    '''
      ~Supervision() {
        static int i = 0;
        KALDI_LOG << "destructor called! " << i;
        i++;
      }
    '''
    # 2. add a `print` statement at the end of `__call__` of `NnetChainExampleDatasetCollateFunc`
    # 3. You will see that the destructor of `chain::Supervision` is called! That is,
    # `for b in dataloader`, the `b` we get contains an empty supervision!
    dataloader = DataLoader(dataset,
                            batch_size=1,
                            num_workers=0,
                            collate_fn=collate_fn)
    for b in dataloader:
        key_list, feature_list, supervision_list = b
        assert feature_list[0].shape == (128, 204, 129) \
            or feature_list[0].shape == (128, 144, 129) \
            or feature_list[0].shape == (128, 165, 129)
        assert supervision_list[0].weight == 1
        supervision_list[0].num_sequences == 128  # minibach size is 128


if __name__ == '__main__':
    _test_nnet_chain_example_dataset()
