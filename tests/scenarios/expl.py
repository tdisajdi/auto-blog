import os, sys, json
os.chdir(sys.argv[1]); sys.path.insert(0, sys.argv[1])
import explainer_engine as xe, topic_engine as te, types
got={}
te.produce_article=lambda **k: got.update(k) or ("publish","t","u")
xe._collect_facts=lambda *a, **k: ("facts", {"SPY":{}}, [{"title":"n","url":"http://u","source":"s"}])
json.dump({"ticker":"GUIDE:%s"%xe.GUIDE_TOPICS[0]["id"],"memo":"메모!"}, open("confirmed_topic_context.json","w"))
ea=types.SimpleNamespace(get_macro_data=lambda: {}, TAX_RULES_BASIS="2025년 세법 기준")
xe.run_explainer("GUIDE:"+xe.GUIDE_TOPICS[0]["id"], ea)
assert got["article_type"]=="guide" and got["memo"]=="메모!" and got["meta"]=={"example_tickers":["SPY"]} and got["category_label"].startswith("ETF/")
assert not os.path.exists("confirmed_topic_context.json")
got.clear(); xe.run_explainer("ISSUE:fx", ea); assert got["article_type"]=="issue" and got["memo"]==""
print("explainer ok")
