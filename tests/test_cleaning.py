import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
from app import clean_dataframe

def test_clean_dataframe():
    df = pd.DataFrame({
        'A': [1, 1, None],
        'B': ['foo', 'foo', 'bar'],
        'Date': ['2021/01/01', '2021/01/01', '2021.01.01']
    })
    cleaned = clean_dataframe(df)
    assert cleaned.shape[0] == 2  # duplicates removed
    assert cleaned['A'].notnull().all()
    assert cleaned['B'].iloc[1] == 'Bar'
    assert cleaned['Date'].iloc[0] == '2021-01-01'
