"""Evaluate independent human document labels; never manufacture missing truth."""
from collections import Counter
from datetime import datetime
from app.services.source_document_classifier import DOCUMENT_TYPES, POLICY_TYPES

def evaluate_classification(labels, predictions):
    accepted={};invalid=0;conflicting=set()
    for row in labels:
        identity=str(row.get('source_id',''))
        try:datetime.fromisoformat(str(row.get('reviewed_at','')).replace('Z','+00:00'))
        except ValueError:invalid+=1;continue
        if (not identity or row.get('label_provenance')!='human' or not row.get('reviewer')
                or row.get('label') not in DOCUMENT_TYPES or identity not in predictions):
            invalid+=1;continue
        if identity in accepted and accepted[identity]['label']!=row['label']:conflicting.add(identity)
        accepted[identity]=row
    for identity in conflicting:accepted.pop(identity,None)
    confusion={};dangerous=0
    for identity,row in accepted.items():
        actual=row['label'];predicted=predictions[identity]
        if predicted not in DOCUMENT_TYPES:raise ValueError('Unknown prediction type')
        counts=confusion.setdefault(actual,{})
        counts[predicted]=counts.get(predicted,0)+1
        dangerous+=int(actual not in POLICY_TYPES and predicted in POLICY_TYPES)
    per_class={}
    for label in DOCUMENT_TYPES:
        tp=confusion.get(label,{}).get(label,0)
        actual=sum(confusion.get(label,{}).values())
        predicted=sum(row.get(label,0) for row in confusion.values())
        per_class[label]={'support':actual,'predicted_n':predicted,'precision':tp/predicted if predicted else None,'recall':tp/actual if actual else None}
    return {'human_n':len(accepted),'invalid_or_unreviewed_n':invalid,'conflicting_source_ids':sorted(conflicting),
        'per_class':per_class,'confusion_matrix':confusion,'dangerous_policy_false_positives':dangerous,
        'calibration_validated':False,'meets_minimum_n':len(accepted)>=50,
        'missing_classes':[k for k,v in per_class.items() if not v['support']]}
