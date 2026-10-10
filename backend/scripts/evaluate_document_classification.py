"""Evaluate a returned human label sheet without replaying or writing any database."""
from pathlib import Path
import argparse,csv,json,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app.services.document_policy_evaluation import evaluate_classification

def main():
 parser=argparse.ArgumentParser()
 parser.add_argument('--labels',type=Path,required=True)
 parser.add_argument('--predictions',type=Path,required=True)
 parser.add_argument('--output',type=Path,required=True)
 args=parser.parse_args()
 labels=list(csv.DictReader(args.labels.open(encoding='utf-8-sig',newline='')))
 sources=json.loads(args.predictions.read_text(encoding='utf-8-sig'))
 result=evaluate_classification(labels,{str(r['source_id']):r['classification']['document_type'] for r in sources})
 args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'human_n':result['human_n'],'meets_minimum_n':result['meets_minimum_n'],'calibration_validated':result['calibration_validated']},ensure_ascii=False))

if __name__=='__main__':main()
