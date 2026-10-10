import importlib
import pytest

def evaluator():
 try:return importlib.import_module('app.services.document_policy_evaluation').evaluate_classification
 except ModuleNotFoundError:pytest.fail('Classification evaluation missing')

def test_unreviewed_or_machine_labels_not_human_metrics():
 rows=[{'source_id':'1','label':'registration_notice','label_provenance':'machine','reviewer':'agent','reviewed_at':'2026-10-01'}]
 result=evaluator()(rows,{'1':'registration_notice'})
 assert result['human_n']==0 and result['confusion_matrix']=={}
 assert result['per_class']['registration_notice']['precision'] is None

def test_real_label_metrics_count_false_policy_positive():
 rows=[{'source_id':str(i),'label':label,'label_provenance':'human','reviewer':'operator','reviewed_at':'2026-10-01T00:00:00Z'} for i,label in enumerate(['registration_notice','registration_notice','policy_recognition_document'])]
 result=evaluator()(rows,{'0':'registration_notice','1':'policy_recognition_document','2':'policy_recognition_document'})
 assert result['human_n']==3
 assert result['per_class']['policy_recognition_document']['precision']==0.5
 assert result['per_class']['registration_notice']['recall']==0.5
 assert result['dangerous_policy_false_positives']==1

def test_duplicate_source_labels_do_not_inflate_n():
 row={'source_id':'a','label':'registration_notice','label_provenance':'human','reviewer':'operator','reviewed_at':'2026-10-01T00:00:00Z'}
 result=evaluator()([row,row],{'a':'registration_notice'})
 assert result['human_n']==1
