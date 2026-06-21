"""粉笔模考复盘工具 - CLI 入口

提供以下命令：
    python main.py init --data-dir <目录>   初始化知识库（批量导入历史报告）
    python main.py analyze --report <文件>   增量分析新模考
"""

import argparse
import glob
import os
import re
import shutil
import sys
from datetime import datetime

from utils.db import KnowledgeDB
from utils.analysis import (
    parse_report,
    extract_exam_info,
    process_report_for_init,
    process_report_for_analyze,
    generate_init_report,
    generate_incremental_report,
    generate_confirmation_sheet,
)


def cmd_init(args):
    """初始化知识库命令。

    扫描指定文件夹中所有 merged_report.json，按日期排序后逐一入库分析，
    最终输出「初始能力画像」报告。
    """
    data_dir = args.data_dir
    if not os.path.isdir(data_dir):
        print(f"❌ 目录不存在：{data_dir}")
        sys.exit(1)

    # 递归查找所有 merged_report.json
    pattern = os.path.join(data_dir, '**', 'merged_report.json')
    report_files = glob.glob(pattern, recursive=True)

    if not report_files:
        print(f"❌ 在 {data_dir} 中未找到任何 merged_report.json 文件")
        sys.exit(1)

    print(f"📂 找到 {len(report_files)} 份报告\n")

    # 解析每份报告，提取日期信息用于排序
    report_info = []
    for fp in report_files:
        try:
            questions = parse_report(fp)
            info = extract_exam_info(questions)
            info['path'] = fp
            report_info.append(info)
        except Exception as e:
            print(f"⚠️ 跳过无法解析的文件：{fp}（{e}）")

    # 按日期排序
    report_info.sort(key=lambda x: x.get('exam_date', '0000-00-00'))

    # 初始化数据库
    db_path = args.db or os.path.join(
        os.path.dirname(__file__), 'data', 'knowledge_base.db'
    )
    db = KnowledgeDB(db_path)

    # 逐一处理
    success_count = 0
    for i, info in enumerate(report_info, 1):
        fp = info['path']
        print(f"[{i}/{len(report_info)}] 处理：{info.get('exam_name', fp)}")
        result = process_report_for_init(
            fp, db, diagnose_errors=args.diagnose
        )
        if result.get('success'):
            success_count += 1
            print(f"  ✅ 入库 {result['total_questions']} 题，"
                  f"正确 {result['correct_questions']} 题")
        else:
            print(f"  ⚠️ {result.get('error', '未知错误')}")

    print(f"\n📊 成功入库 {success_count}/{len(report_info)} 份报告")

    # 生成能力画像报告
    report = generate_init_report(db)
    print("\n" + "=" * 60)
    print(report)

    # 保存报告
    report_dir = os.path.join(os.path.dirname(__file__), 'data')
    report_file = os.path.join(
        report_dir,
        f"init_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    )
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"\n📁 报告已保存至：{report_file}")

    db.close()
    print("✅ 初始化完成！")


def cmd_analyze(args):
    """增量分析命令。

    处理一份新的 merged_report.json，进行：
    1. 备份到 data/reports/
    2. 更新数据库
    3. 调用 LLM 诊断错题（可选）
    4. 生成标签确认单
    5. 生成复盘报告
    """
    report_path = args.report
    if not os.path.isfile(report_path):
        print(f"❌ 文件不存在：{report_path}")
        sys.exit(1)

    print(f"📄 分析报告：{report_path}")

    # 解析基本信息
    questions = parse_report(report_path)
    if not questions:
        print("❌ 报告为空或无法解析")
        sys.exit(1)

    exam_info = extract_exam_info(questions)
    print(f"   试卷：{exam_info['exam_name']}")
    print(f"   题目数：{exam_info['total_questions']}")
    print(f"   正确：{exam_info['correct_questions']}")

    # 备份到标准目录
    now = datetime.now()
    safe_name = re.sub(r'[<>:"/\\|?*\s]+', '_', exam_info['exam_name'] or 'unknown')[:50]
    backup_dir = os.path.join(
        os.path.dirname(__file__), 'data', 'reports',
        f"{now.strftime('%Y-%m-%d_%H-%M-%S')}_{safe_name}"
    )
    os.makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(backup_dir, 'merged_report.json')
    shutil.copy2(report_path, backup_path)
    print(f"📁 已备份至：{backup_path}")

    # 数据库操作
    db_path = args.db or os.path.join(
        os.path.dirname(__file__), 'data', 'knowledge_base.db'
    )
    db = KnowledgeDB(db_path)

    # 检查是否已入库
    if db.exam_exists(backup_path):
        print("⚠️ 该报告已入库，将使用已有记录")
        report_path_to_use = backup_path
    else:
        report_path_to_use = backup_path

    # 处理报告
    print("\n🔄 处理报告数据...")
    result = process_report_for_analyze(
        report_path_to_use, db, diagnose_errors=args.diagnose
    )

    if not result.get('success'):
        print(f"❌ 处理失败：{result.get('error', '未知错误')}")
        db.close()
        sys.exit(1)

    print(f"✅ 已处理 {result['total_questions']} 题")

    # 生成诊断确认单
    if args.diagnose and result.get('pending_count', 0) > 0:
        print(f"\n📝 生成诊断确认单（{result['pending_count']} 项待确认）...")
        sheet = generate_confirmation_sheet(db, report_path_to_use)
        sheet_file = os.path.join(
            backup_dir,
            f"diagnosis_confirmation_{now.strftime('%Y%m%d_%H%M%S')}.md"
        )
        with open(sheet_file, 'w', encoding='utf-8') as f:
            f.write(sheet)
        print(f"📁 确认单已保存至：{sheet_file}")
        print("\n请打开确认单，标注接受/修改，然后通过以下方式确认：")
        print(f"  1. 在 Streamlit 界面中手动确认")
        print(f"  2. 直接编辑数据库（通过 sqlite3）")
        print(f"  3. 运行 python main.py confirm --report \"{report_path_to_use}\"")

    # 生成增量报告
    print("\n📊 生成复盘报告...")
    prev_exams = db.get_exam_records()
    prev_exam = prev_exams[1] if len(prev_exams) > 1 else None  # 上一次模考

    report = generate_incremental_report(
        current_exam=exam_info,
        previous_exam=prev_exam,
        db=db,
    )
    print("\n" + "=" * 60)
    print(report)

    report_file = os.path.join(
        backup_dir,
        f"review_report_{now.strftime('%Y%m%d_%H%M%S')}.md"
    )
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"\n📁 复盘报告已保存至：{report_file}")

    db.close()
    print("✅ 分析完成！")


def cmd_confirm(args):
    """确认诊断结果命令。

    从确认单（Markdown 文件）中读取确认项，批量更新数据库。
    或者直接通过命令行交互确认。
    """
    report_path = args.report
    db_path = args.db or os.path.join(
        os.path.dirname(__file__), 'data', 'knowledge_base.db'
    )
    db = KnowledgeDB(db_path)

    pending = db.get_pending_diagnoses(report_path)

    if not pending:
        print("✅ 没有待确认的诊断项。")
        db.close()
        return

    print(f"共 {len(pending)} 项待确认\n")

    for i, p in enumerate(pending, 1):
        qa = db.get_question_by_key(p['question_key'])
        q_info = ""
        if qa:
            q_info = (
                f"你的答案：{qa.get('your_answer', '?')}，"
                f"正确答案：{qa.get('correct_answer', '?')}"
            )

        print(f"[{i}/{len(pending)}] {p['question_key']} {q_info}")
        if p.get('specific_error'):
            print(f"   错因：{p['specific_error']}")
        if p.get('countermeasure'):
            print(f"   对策：{p['countermeasure']}")
        print(f"   置信度：{p['confidence']:.0%}")

        choice = input("   接受？[Y/n]：").strip()
        if choice.lower() == 'n':
            print("   ⏭️ 跳过")
            continue
        else:
            db.confirm_diagnosis(p['id'])
            print("   ✅ 已确认")

    db.close()
    print("\n✅ 确认完成！")


def cmd_report(args):
    """单独生成报告命令。"""
    db_path = args.db or os.path.join(
        os.path.dirname(__file__), 'data', 'knowledge_base.db'
    )
    db = KnowledgeDB(db_path)

    if args.type == 'init':
        report = generate_init_report(db)
    elif args.type == 'incremental' and args.report:
        questions = parse_report(args.report)
        exam_info = extract_exam_info(questions)
        prev_exams = db.get_exam_records()
        prev_exam = prev_exams[1] if len(prev_exams) > 1 else None
        report = generate_incremental_report(exam_info, prev_exam, db)
    else:
        print("❌ 请指定 --type init 或 --type incremental --report <路径>")
        db.close()
        sys.exit(1)

    print(report)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"\n📁 报告已保存至：{args.output}")

    db.close()


def main():
    parser = argparse.ArgumentParser(
        description='粉笔模考复盘工具 - 知识库管理与分析'
    )
    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # init 命令
    parser_init = subparsers.add_parser('init', help='初始化知识库')
    parser_init.add_argument(
        '--data-dir', '-d', required=True,
        help='包含多份历史 merged_report.json 的文件夹'
    )
    parser_init.add_argument(
        '--db', help='数据库路径（默认 data/knowledge_base.db）'
    )
    parser_init.add_argument(
        '--diagnose', action='store_true',
        help='在初始化时也调用 LLM 诊断错题（耗时较长）'
    )
    parser_init.set_defaults(func=cmd_init)

    # analyze 命令
    parser_analyze = subparsers.add_parser('analyze', help='增量分析新模考')
    parser_analyze.add_argument(
        '--report', '-r', required=True,
        help='新 merged_report.json 路径'
    )
    parser_analyze.add_argument(
        '--db', help='数据库路径（默认 data/knowledge_base.db）'
    )
    parser_analyze.add_argument(
        '--diagnose', action='store_true', default=True,
        help='调用 LLM 诊断错题（默认启用）'
    )
    parser_analyze.add_argument(
        '--no-diagnose', action='store_false', dest='diagnose',
        help='跳过 LLM 诊断'
    )
    parser_analyze.set_defaults(func=cmd_analyze)

    # confirm 命令
    parser_confirm = subparsers.add_parser('confirm', help='确认诊断结果')
    parser_confirm.add_argument(
        '--report', '-r',
        help='报告路径（只确认该报告的待确认项）'
    )
    parser_confirm.add_argument(
        '--db', help='数据库路径'
    )
    parser_confirm.set_defaults(func=cmd_confirm)

    # report 命令（单独生成报告）
    parser_report = subparsers.add_parser('report', help='单独生成分析报告')
    parser_report.add_argument(
        '--type', '-t', choices=['init', 'incremental'], default='init',
        help='报告类型'
    )
    parser_report.add_argument(
        '--report', '-r', help='报告路径（incremental 类型需要）'
    )
    parser_report.add_argument(
        '--db', help='数据库路径'
    )
    parser_report.add_argument(
        '--output', '-o', help='输出文件路径'
    )
    parser_report.set_defaults(func=cmd_report)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == '__main__':
    main()
