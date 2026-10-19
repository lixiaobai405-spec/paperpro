"""Partial-label BIO objectives and degeneration checks (no model training)."""
from __future__ import annotations

from itertools import product
import math

import numpy as np
import pytest

from app.diagnosis.partial_bio import BIO_TAGS
from app.diagnosis.partial_bio_objective import (
    partial_crf_nll, masked_token_nll, supervised_argmax_errors,
    probe_degenerate_decoders,
)
from tests.test_partial_bio import _contact_fixture, _truth
from app.diagnosis.partial_bio import build_partial_bio


def _flat(lines):
    return [part for line in lines for part in line["tags"]]


def test_constrained_log_partition_matches_exact_enumeration():
    tags = [None, "B-WORK_ROLE", "I-WORK_ROLE", "O"]
    mask = [tag is not None for tag in tags]
    logits = np.array([
        [0.2, 0.4, -0.3, 0.1, -0.1, -0.5, 0.2],
        [0.5, 0.8, 0.4, -0.2, 0.0, -0.1, 0.1],
        [-0.2, -0.1, 1.1, 0.2, 0.3, 0.1, -0.3],
        [0.3, 0.2, 0.1, -0.2, -0.7, -0.8, 0.1],
    ])
    reference_full = []
    reference_compatible = []
    def legal(sequence):
        for pos, curr in enumerate(sequence):
            if not curr.startswith("I-"):
                continue
            if pos == 0 or sequence[pos-1] not in (
                "B-"+curr[2:], "I-"+curr[2:]
            ):
                return False
        return True

    for indices in product(range(len(BIO_TAGS)), repeat=len(tags)):
        sequence = [BIO_TAGS[index] for index in indices]
        if not legal(sequence):
            continue
        score = float(sum(logits[i,index] for i,index in enumerate(indices)))
        reference_full.append(score)
        if all((not mask[i] or sequence[i] == tags[i]) for i in range(len(tags))):
            reference_compatible.append(score)

    def logsumexp(values):
        a = max(values)
        return a + math.log(sum(math.exp(value-a) for value in values))

    correct = logsumexp(reference_full)-logsumexp(reference_compatible)
    assert partial_crf_nll(logits, tags, mask) == pytest.approx(correct, abs=1e-9)
    assert correct >= 0


def test_unknown_positions_stay_unconstrained_and_empty_supervision_zero():
    zero = np.zeros((3,len(BIO_TAGS)), dtype=float)
    assert partial_crf_nll(zero,[None]*3,[False]*3) == pytest.approx(0.0,abs=1e-12)
    assert masked_token_nll(zero,[None]*3,[False]*3) == 0
    a = zero.copy()
    b = zero.copy()
    a[1,BIO_TAGS.index("O")] = 8
    b[1,BIO_TAGS.index("B-EMPLOYER")] = 8
    # Only the last character has a confirmed O label. Unknown positions
    # have no artificial O supervision in a masked *token* loss.
    tags = [None, None, "O"]
    observed=[False,False,True]
    assert masked_token_nll(a,tags,observed) == pytest.approx(
        masked_token_nll(b,tags,observed),abs=1e-10
    )


def test_invalid_bio_start_and_mask_mismatch_rejected():
    logits = np.zeros((2,len(BIO_TAGS)))
    with pytest.raises(ValueError,match="BIO"):
        partial_crf_nll(logits,["I-EMPLOYER","O"],[True,True])
    with pytest.raises(ValueError,match="掩码"):
        partial_crf_nll(logits,[None,"O"],[True,True])
    with pytest.raises(ValueError,match="维度"):
        partial_crf_nll(np.zeros((2,2)),["O","O"],[True,True])
    with pytest.raises(ValueError,match="有限"):
        partial_crf_nll(np.array([[float("nan")]*len(BIO_TAGS)]*2),
                        ["O","O"],[True,True])


def test_all_entity_and_all_background_are_rejected_by_real_observed_labels():
    pdf = _contact_fixture()
    truth = {
        **_truth(),
        "basicInfo":{
            "personalEmail":"lab@example.invalid",
            "phoneNumber":"+86 138-0013-8000"
        }
    }
    bundle=build_partial_bio(
        pdf,truth,source_id=21,
        allowed_train_ids=(21,),forbidden_ids=(41,)
    )
    data=probe_degenerate_decoders([bundle])
    assert data["known_entity_chars"]>0
    assert data["verified_O_chars"]>0
    assert data["all_O"]["observed_errors"]>=data["known_entity_chars"]
    assert data["all_work_role"]["observed_errors"]>=data["verified_O_chars"]
    assert data["all_O"]["accepted"] is False
    assert data["all_work_role"]["accepted"] is False
    assert data["local_memorizer_O_unknown"]["observed_errors"]==0
    assert data["local_memorizer_work_role_unknown"]["observed_errors"]==0
    assert data["local_memorizer_O_unknown"]["accepted_for_deployment"] is False
    assert data["local_memorizer_work_role_unknown"]["accepted_for_deployment"] is False
    assert data["unknown_positions_identifiable"] is False
    assert data["unknown_disagreement_chars_between_known_fit_strategies"] == data["unknown_chars"]
    assert data["promotion_gate"]["pass"] is False
    assert data["promotion_gate"]["frozen_holdout_access_allowed"] is False
    assert data["promotion_gate"]["training_or_deployment_authorized"] is False
    assert data["model_training_performed"] is False
    assert data["GT_strings_exported"] is False


def test_impossible_bio_transition_with_known_labels_fails():
    emissions=np.zeros((3,len(BIO_TAGS)))
    with pytest.raises(ValueError,match="BIO"):
        partial_crf_nll(
            emissions,["B-EMPLOYER","I-WORK_ROLE","O"],
            [True,True,True]
        )


def test_lexical_offsets_not_necessary_for_loss_and_error_counter():
    tags=[None,"B-EMPLOYER","I-EMPLOYER","O"]
    mask=[False,True,True,True]
    logits=np.zeros((4,len(BIO_TAGS)))
    for i,tag in enumerate(tags):
        if tag is not None:
            logits[i,BIO_TAGS.index(tag)] = 8
    assert supervised_argmax_errors(logits,tags,mask)==0
    assert masked_token_nll(logits,tags,mask)>0
    logits[0,:] = 1000  # unknown character must not create a fake label
    assert supervised_argmax_errors(logits,tags,mask)==0
