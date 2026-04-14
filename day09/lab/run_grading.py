import json
import os
import sys
from datetime import datetime

# Đảm bảo import được các module trong thư mục lab
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from graph import run_graph

def run_grading():
    questions_file = "data/grading_questions.json"
    output_file = "artifacts/grading_run.jsonl"
    
    if not os.path.exists(questions_file):
        print(f"❌ Không tìm thấy file: {questions_file}")
        return

    # Khởi tạo thư mục artifacts nếu chưa có
    os.makedirs("artifacts", exist_ok=True)

    with open(questions_file, encoding="utf-8") as f:
        questions = json.load(f)

    print(f"🚀 Bắt đầu chạy GRADING cho {len(questions)} câu hỏi...")
    print(f"📝 Kết quả sẽ được lưu tại: {output_file}")
    print("-" * 50)

    with open(output_file, "w", encoding="utf-8") as out:
        for i, q in enumerate(questions, 1):
            q_id = q.get("id", f"gq{i:02d}")
            question_text = q["question"]
            
            print(f"[{i}/{len(questions)}] Đang xử lý {q_id}...")
            
            try:
                # Chạy pipeline multi-agent
                result = run_graph(question_text)
                
                # Format đúng chuẩn grading yêu cầu
                record = {
                    "id": q_id,
                    "question": question_text,
                    "answer": result.get("final_answer", ""),
                    "sources": result.get("retrieved_sources", []),
                    "supervisor_route": result.get("supervisor_route", ""),
                    "route_reason": result.get("route_reason", ""),
                    "workers_called": result.get("workers_called", []),
                    "mcp_tools_used": [t.get("tool") if isinstance(t, dict) else t for t in result.get("mcp_tools_used", [])],
                    "confidence": result.get("confidence", 0.0),
                    "hitl_triggered": result.get("hitl_triggered", False),
                    "timestamp": datetime.now().isoformat()
                }
                status = "✅ Thành công"
            except Exception as e:
                print(f"  ❌ Lỗi tại {q_id}: {e}")
                record = {
                    "id": q_id,
                    "question": question_text,
                    "answer": f"PIPELINE_ERROR: {str(e)}",
                    "sources": [],
                    "supervisor_route": "error",
                    "route_reason": str(e),
                    "workers_called": [],
                    "mcp_tools_used": [],
                    "confidence": 0.0,
                    "hitl_triggered": False,
                    "timestamp": datetime.now().isoformat()
                }
                status = "❌ Thất bại"

            # Ghi vào file JSONL (mỗi dòng 1 object)
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            
    print("-" * 50)
    print(f"✨ Hoàn thành! Vui lòng kiểm tra file {output_file}")
    print("⚠️  Lưu ý: Bạn phải nộp file .jsonl này trước 18:00.")

if __name__ == "__main__":
    run_grading()
