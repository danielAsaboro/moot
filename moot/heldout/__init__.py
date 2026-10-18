"""Study H1: a held-out evaluation on real decisions, graded by what their own teams later did (docs/studies.md).

  python3 -m moot.heldout.gold     units, independent gold, frozen dev/test split and its hash -> eval/heldout/gold.json
  python3 -m moot.heldout.inputs   what each system may see at the cut date -> data/heldout/inputs.json
  python3 eval/eval_heldout.py     every arm, scored on the test split -> eval/results_heldout.{md,json}
"""
