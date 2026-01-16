import json
import os
import sys

from app.db.session import SessionLocal  
# 2. 모델 가져오기 (이건 확실함)
from app.db.models import Stock

def init_stock_data():
    # 파일이 같은 폴더에 있다고 가정
    file_path = "DomesticStocks.json"
    
    print(f"📂 {file_path} 읽는 중...")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data_list = json.load(f)
    except FileNotFoundError:
        print("❌ JSON 파일이 없어요! insert_stocks.py 바로 옆에 두셨나요?")
        return

    db = SessionLocal()
    
    try:
        print(f"🚀 {len(data_list)}개 데이터 DB 입력 시작...")
        
        stocks_to_insert = []
        for item in data_list:
            stock = Stock(
                stock_id=item["Code"],
                stock_name=item["Name"]
            )
            stocks_to_insert.append(stock)

        # 데이터 넣기
        db.add_all(stocks_to_insert)
        db.commit()
        print("✅ 성공! 모든 주식 데이터가 들어갔습니다.")

    except Exception as e:
        print(f"❌ 에러 발생: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    init_stock_data()