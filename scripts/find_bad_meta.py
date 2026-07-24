#!/usr/bin/env python3
import pickle, glob, os, json
bad_missing_lstm=[]
bad_lstm_one=[]
other_errors=0
total=0
for p in glob.glob('saved_meta/**/*.pkl', recursive=True):
    try:
        m=pickle.load(open(p,'rb'))
    except Exception:
        other_errors+=1
        continue
    total+=1
    rel=os.path.relpath(p)
    if not isinstance(m, dict) or 'lstm_history' not in m or not m.get('lstm_history'):
        bad_missing_lstm.append(rel)
        continue
    h=m.get('lstm_history')
    acc = None
    if isinstance(h, dict):
        acc = h.get('accuracy') or h.get('acc')
    if isinstance(acc, (list,tuple)) and len(acc)>0:
        try:
            if float(acc[0])==1.0:
                bad_lstm_one.append(rel)
        except Exception:
            pass
out={
    'total_meta': total,
    'other_errors': other_errors,
    'missing_lstm_count': len(bad_missing_lstm),
    'lstm_one_count': len(bad_lstm_one),
    'missing_lstm_sample': bad_missing_lstm[:100],
    'lstm_one_sample': bad_lstm_one[:100]
}
print(json.dumps(out, indent=2))
