import json
import os
import pandas as pd
from tqdm import tqdm  # 进度条库，如果没有安装请运行: pip install tqdm

# ================= 配置路径 =================
# 获取项目根目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DATA_DIR = os.path.join(BASE_DIR, 'data', 'raw', 'CAIL2019')
PROCESSED_DIR = os.path.join(BASE_DIR, 'data', 'processed')

# 确保输出目录存在
os.makedirs(PROCESSED_DIR, exist_ok=True)

def extract_correct_text(item):
    """
    根据数据集逻辑，提取正确的案情文本。
    item 结构: {'A': '文本...', 'B': '文本...', 'C': '文本...', 'label': 'C'}
    我们需要提取 label 指向的那个文本。
    """
    correct_key = item.get('label')
    if not correct_key:
        return None
    
    # 获取对应的文本
    text = item.get(correct_key)
    return text

def process_cail_file(file_name, output_name):
    """
    读取单个 CAIL2019 JSON 文件并转换为 CSV
    """
    file_path = os.path.join(RAW_DATA_DIR, file_name)
    
    if not os.path.exists(file_path):
        print(f"⚠️ 文件不存在: {file_path}")
        return

    print(f"正在处理: {file_name} ...")
    data_list = []
    
    # CAIL2019 数据通常较大，建议逐行读取
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in tqdm(f):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                
                # === 核心修改：提取正确文本 ===
                text = extract_correct_text(item)
                
                # 如果没有提取到文本，尝试使用 A 作为默认值（容错处理）
                if not text:
                    text = item.get('A', '')

                # 简单清洗：过滤过短的文本
                if len(text) < 50:
                    continue
                
                # 构造结构化数据
                # 对于合同审计任务，我们将案情描述作为输入文本
                data_list.append({
                    "text": text,           # 模型输入 (案情/合同背景)
                    "risk_label": item.get('label', ''), # 保留原始标签 (A/B/C)
                    "source": "CAIL2019"
                })
            except Exception as e:
                # 打印错误但不中断流程
                print(f"\n解析错误: {e}")
                continue

    if not data_list:
        print(f"⚠️ 警告: {file_name} 未能提取到任何数据，请检查文件格式！")
        return

    # 转换为 DataFrame
    df = pd.DataFrame(data_list)
    
    # 保存为 CSV
    output_path = os.path.join(PROCESSED_DIR, output_name)
    df.to_csv(output_path, index=False, encoding='utf-8')
    print(f"✅ 已保存: {output_path} (共 {len(df)} 条数据)")

def main():
    print("====== 开始 CAIL2019 数据预处理 ======")
    
    # 1. 处理训练集
    process_cail_file('train.json', 'train.csv')
    
    # 2. 处理验证集
    process_cail_file('valid.json', 'val.csv')
    
    # 3. 处理测试集
    process_cail_file('test.json', 'test.csv')
    
    print("\n====== 所有数据处理完成！======")
    print(f"处理后的文件位于: {PROCESSED_DIR}")

if __name__ == "__main__":
    main()
