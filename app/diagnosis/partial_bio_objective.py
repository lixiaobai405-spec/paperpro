"""Exact partial-label BIO objective and transparent degeneracy diagnostics.

Research-only, CPU NumPy. Not a model, optimizer, or production inference path.

For a line with emission logits E and BIO-legal tag sequences Y:
    NLL = logsumexp_{y in Y} score(y) -
          logsumexp_{y in Y, y_observed = GT_observed} score(y).

UNKNOWN characters are *marginalized*, never treated as O. Transition rules
are the usual legal BIO rules with zero transition score for allowed edges.
There are no learned transition parameters, no hidden background heuristic,
no self-generated supervision and no parameter update in this module.

Known GT is incomplete. Even a low partial-label NLL cannot prove correct
predictions at UNKNOWN positions. In particular, the local-memorizer
degeneracy probes can fit observed positions while predicting arbitrary
UNKNOWN backgrounds or entities; neither is deployable.
"""
from __future__ import annotations

import numpy as np

from .partial_bio import BIO_TAGS

_TAGS = tuple(BIO_TAGS)
_N = len(_TAGS)
_TAG_INDEX = {value:i for i,value in enumerate(_TAGS)}
_BEGINS = np.asarray([
    not item.startswith("I-") for item in _TAGS
],dtype=bool)
_TRANSITIONS = np.zeros((_N,_N),dtype=bool)
for i,previous in enumerate(_TAGS):
    for j,current in enumerate(_TAGS):
        _TRANSITIONS[i,j] = (
            not current.startswith("I-")
            or previous in ("B-"+current[2:],"I-"+current[2:])
        )
_TRANSITION_SCORES = np.where(_TRANSITIONS,0.0,-np.inf)
_START_SCORES = np.where(_BEGINS,0.0,-np.inf)


def _validate(
    emissions, observed_tags:list[str|None], observed_mask:list[bool]
) -> np.ndarray:
    data=np.asarray(emissions,dtype=np.float64)
    if data.ndim!=2 or data.shape!=(len(observed_tags),_N) or (
        len(observed_tags)!=len(observed_mask)
    ):
        raise ValueError("部分 BIO 发射矩阵维度不正确")
    if not np.all(np.isfinite(data)):
        raise ValueError("BIO 发射分数必须为有限实数")
    for tag,mask in zip(observed_tags,observed_mask):
        if type(mask) not in (bool,np.bool_) or (tag is not None)!=bool(mask) or (
            tag is not None and tag not in _TAG_INDEX
        ):
            raise ValueError("BIO 标签与观察掩码不一致")
    return data


def _partition(data:np.ndarray,tags:list[str|None]|None) -> float:
    """Stable forward log-partition over all BIO-legal paths."""
    if len(data)==0:
        return 0.0
    alpha=_START_SCORES+data[0]
    if tags is not None and tags[0] is not None:
        mask=np.asarray([value==tags[0] for value in _TAGS])
        alpha=np.where(mask,alpha,-np.inf)
    for index in range(1,len(data)):
        alpha=np.logaddexp.reduce(alpha[:,None]+_TRANSITION_SCORES,axis=0)+data[index]
        if tags is not None and tags[index] is not None:
            allowed=np.asarray([value==tags[index] for value in _TAGS])
            alpha=np.where(allowed,alpha,-np.inf)
    return float(np.logaddexp.reduce(alpha))


def partial_crf_nll(emissions,observed_tags,observed_mask) -> float:
    """Negative log probability of all sequences matching observed labels.

    Unknown positions remain unconstrained and are marginalized by the
    forward algorithm. This is NOT a conventional full-label CRF loss.
    """
    data=_validate(emissions,observed_tags,observed_mask)
    if not any(observed_mask):
        return 0.0
    z_full=_partition(data,None)
    z_observed=_partition(data,list(observed_tags))
    if not np.isfinite(z_observed):
        raise ValueError("BIO 已知标签没有合法路径")
    return float(max(0.0,z_full-z_observed))


def masked_token_nll(emissions,observed_tags,observed_mask) -> float:
    """Known-tag-only token cross-entropy; UNKNOWN contributes exactly zero.

    Loss is averaged over *known* characters, unlike partial CRF which sums
    sequence likelihood. This deliberately ignores all BIO transitions and
    is included as a numerical/identifiability control.
    """
    data=_validate(emissions,observed_tags,observed_mask)
    indices=[i for i,m in enumerate(observed_mask) if m]
    if not indices:
        return 0.0
    subset=data[indices]
    maximum=subset.max(axis=1)
    denom=maximum+np.log(np.exp(subset-maximum[:,None]).sum(axis=1))
    correct=subset[
        np.arange(len(indices)),[
            _TAG_INDEX[observed_tags[index]] for index in indices
        ]
    ]
    return float(np.mean(denom-correct))


def supervised_argmax_errors(emissions,observed_tags,observed_mask) -> int:
    """Diagnostic observed-label disagreements, not sequence-level accuracy."""
    data=_validate(emissions,observed_tags,observed_mask)
    choices=np.argmax(data,axis=1)
    return sum(
        int(choices[index]!=_TAG_INDEX[tag])
        for index,(tag,observed) in enumerate(
            zip(observed_tags,observed_mask)
        ) if observed
    )


def _probe_logits(
    tags:list[str|None],observed_mask:list[bool],
    strategy:str, margin:float
) -> np.ndarray:
    logits=np.full((len(tags),_N),-margin,dtype=float)
    if strategy in ("all_O","all_work_role"):
        tag="O" if strategy=="all_O" else "B-WORK_ROLE"
        logits[:,_TAG_INDEX[tag]]=margin
    elif strategy in (
        "local_memorizer_O_unknown","local_memorizer_work_role_unknown"
    ):
        unknown="O" if strategy=="local_memorizer_O_unknown" else "B-WORK_ROLE"
        logits[:,_TAG_INDEX[unknown]]=margin
        for i,(tag,known) in enumerate(zip(tags,observed_mask)):
            if known:
                logits[i,:]=-margin
                logits[i,_TAG_INDEX[tag]]=margin
    else:
        raise ValueError("未知退化策略")
    return logits


def probe_degenerate_decoders(
    bundles:list[dict], *, margin:float=7.0
) -> dict:
    """Evaluate four fixed degeneration strategies with no parameter fitting.

    The apparent known-label agreement of the two 'local memorizers' does
    not resolve unknown-position identity or justify deployment.
    """
    if not bundles or not np.isfinite(margin) or not 1<=margin<=20:
        raise ValueError("需要已标注数据和有限的退化测试幅度")
    from .partial_bio import summarize_partial_bio
    verified=summarize_partial_bio(bundles)
    known_o=verified["observed_O_count"]
    known_positive=verified["known_positive_characters"]
    strategies=(
        "all_O","all_work_role",
        "local_memorizer_O_unknown","local_memorizer_work_role_unknown"
    )
    accumulated={
        name:{"observed_errors":0,"masked_ce_weighted":0.0,
              "partial_crf_nll_sum":0.0}
        for name in strategies
    }
    n_known=known_o+known_positive
    for bundle in bundles:
        for line in bundle["lines"]:
            tags=line["tags"]
            mask=line["observed_mask"]
            local_known=sum(mask)
            if not local_known:
                continue
            for name in strategies:
                logits=_probe_logits(tags,mask,name,margin)
                aggregate=accumulated[name]
                aggregate["observed_errors"]+=supervised_argmax_errors(
                    logits,tags,mask
                )
                aggregate["masked_ce_weighted"]+=masked_token_nll(
                    logits,tags,mask
                )*local_known
                aggregate["partial_crf_nll_sum"]+=partial_crf_nll(
                    logits,tags,mask
                )
    result={
        "kind":"partial_BIO_objective_degeneracy_probe",
        "sources":verified["sources"],
        "known_entity_chars":known_positive,
        "verified_O_chars":known_o,
        "unknown_chars":verified["unknown_characters"],
        "known_character_fraction":verified["supervised_character_fraction"],
        "unknown_positions_identifiable":False,
        "unknown_disagreement_chars_between_known_fit_strategies":verified["unknown_characters"],
        "unknown_disagreement_fraction":round(
            verified["unknown_characters"]/(
                verified["unknown_characters"]+n_known
            ),6
        ),
        "complete_sequence_labels_available":False,
        "model_training_performed":False,
        "GT_strings_exported":False,
        "deployed":False,
    }
    for name,metrics in accumulated.items():
        m={
            "observed_errors":metrics["observed_errors"],
            "observed_error_rate":round(
                metrics["observed_errors"]/n_known,6
            ),
            "masked_token_nll_per_known":round(
                metrics["masked_ce_weighted"]/n_known,6
            ),
            "partial_crf_nll_sum":round(
                metrics["partial_crf_nll_sum"],6
            ),
        }
        if name.startswith("local_memorizer"):
            m["accepted_for_deployment"]=False
            m["reason"]="Perfect known-label fitting cannot identify UNKNOWN labels"
        else:
            m["accepted"]=metrics["observed_errors"]==0
        result[name]=m
    result["promotion_gate"]={
        "pass":False,
        "reason":"两种未知位置相反的预测均满足已观测监督，无法证明未标注位置的拒识能力；缺少独立端到端验证",
        "frozen_holdout_access_allowed":False,
        "training_or_deployment_authorized":False,
    }
    return result
