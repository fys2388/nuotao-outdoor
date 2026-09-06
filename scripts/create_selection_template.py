#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nuotao Outdoor 选品评分模板生成器 V2.0
生成11维度选品评分Excel模板
"""

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

def create_selection_template():
    wb = openpyxl.Workbook()
    
    # ========== Sheet 1: 选品评分表 ==========
    ws1 = wb.active
    ws1.title = "选品评分表"
    
    # 样式定义
    header_font = Font(name='微软雅黑', size=12, bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color='2F5496', end_color='2F5496', fill_type='solid')
    sub_header_font = Font(name='微软雅黑', size=11, bold=True, color='000000')
    sub_header_fill = PatternFill(start_color='D6E4F0', end_color='D6E4F0', fill_type='solid')
    normal_font = Font(name='微软雅黑', size=10)
    center_align = Alignment(horizontal='center', vertical='center', wrap_text=True)
    left_align = Alignment(horizontal='left', vertical='center', wrap_text=True)
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    # A级绿色，B级蓝色，C级黄色，D级红色
    grade_a_fill = PatternFill(start_color='C6EFCE', end_color='C6EFCE', fill_type='solid')
    grade_b_fill = PatternFill(start_color='BDD7EE', end_color='BDD7EE', fill_type='solid')
    grade_c_fill = PatternFill(start_color='FFEB9C', end_color='FFEB9C', fill_type='solid')
    grade_d_fill = PatternFill(start_color='FFC7CE', end_color='FFC7CE', fill_type='solid')
    
    # 标题行
    ws1.merge_cells('A1:H1')
    ws1['A1'] = 'Nuotao Outdoor 选品评分表 V2.0（11维度评分体系）'
    ws1['A1'].font = Font(name='微软雅黑', size=14, bold=True, color='FFFFFF')
    ws1['A1'].fill = PatternFill(start_color='1F3864', end_color='1F3864', fill_type='solid')
    ws1['A1'].alignment = center_align
    ws1.row_dimensions[1].height = 30
    
    # 产品基本信息
    info_headers = ['产品名称', '1688 Offer ID', '采购价(¥)', '目标售价($)', '供应商', '选品日期', '产品系列', '备注']
    for col, header in enumerate(info_headers, 1):
        cell = ws1.cell(row=2, column=col, value=header)
        cell.font = sub_header_font
        cell.fill = sub_header_fill
        cell.alignment = center_align
        cell.border = thin_border
    
    # 11维度评分表头
    score_headers = [
        ('维度', 20), ('权重', 8), ('得分(0-100)', 12), ('加权分', 10), ('评分标准/备注', 50)
    ]
    
    start_row = 4
    ws1.merge_cells(f'A{start_row}:E{start_row}')
    ws1[f'A{start_row}'] = '11维度评分明细'
    ws1[f'A{start_row}'].font = header_font
    ws1[f'A{start_row}'].fill = header_fill
    ws1[f'A{start_row}'].alignment = center_align
    
    for col, (header, width) in enumerate(score_headers, 1):
        cell = ws1.cell(row=start_row+1, column=col, value=header)
        cell.font = sub_header_font
        cell.fill = sub_header_fill
        cell.alignment = center_align
        cell.border = thin_border
        ws1.column_dimensions[get_column_letter(col)].width = width
    
    # 11维度数据
    dimensions = [
        ('1. 供应商资质', '15%', '', '', '超级工厂?入驻年限?回头率?品质达标率?'),
        ('2. 销量验证', '10%', '', '', '全网销量?月销?复购率?'),
        ('3. 全成本利润率', '15%', '', '', '采购价+国际物流+平台费+营销费，全成本利润率>60%优秀'),
        ('4. 产品质量', '10%', '', '', '品质达标率?48小时发货率?退货率?'),
        ('5. 物流支持', '5%', '', '', '包邮?退货包运费?一件代发?3天达?'),
        ('6. 差异化空间', '5%', '', '', '原图合规性?AI生图提升空间?'),
        ('7. 市场热度', '10%', '', '', 'Google Trends趋势?TikTok播放量?亚马逊BSR?'),
        ('8. 亚马逊竞争度', '10%', '', '', '搜索结果数?Top10 Review数?平均售价?垄断品牌?'),
        ('9. 季节性适配', '5%', '', '', '旺季时长?当前所处季节?最佳上架时机?'),
        ('10. AI生图难度', '5%', '', '', '结构复杂度?材质表现?细节还原?I2I参考图质量?'),
        ('11. 合规与侵权风险', '5%', '', '', '专利?商标?认证?材质合规?标签合规?'),
    ]
    
    for i, (dim, weight, score, weighted, note) in enumerate(dimensions):
        row = start_row + 2 + i
        ws1.cell(row=row, column=1, value=dim).font = normal_font
        ws1.cell(row=row, column=2, value=weight).font = normal_font
        ws1.cell(row=row, column=3, value=score).font = normal_font
        ws1.cell(row=row, column=4, value=f'=B{row}*C{row}/100').font = normal_font
        ws1.cell(row=row, column=5, value=note).font = normal_font
        
        for col in range(1, 6):
            ws1.cell(row=row, column=col).alignment = left_align if col == 5 else center_align
            ws1.cell(row=row, column=col).border = thin_border
    
    # 总分和等级
    total_row = start_row + 2 + len(dimensions)
    ws1.cell(row=total_row, column=1, value='综合总分').font = Font(name='微软雅黑', size=11, bold=True)
    ws1.cell(row=total_row, column=1).fill = sub_header_fill
    ws1.cell(row=total_row, column=4, value=f'=SUM(D{start_row+2}:D{total_row-1})').font = Font(name='微软雅黑', size=12, bold=True)
    ws1.cell(row=total_row, column=4).fill = PatternFill(start_color='FFF2CC', end_color='FFF2CC', fill_type='solid')
    
    grade_row = total_row + 1
    ws1.cell(row=grade_row, column=1, value='选品等级').font = Font(name='微软雅黑', size=11, bold=True)
    ws1.cell(row=grade_row, column=1).fill = sub_header_fill
    ws1.cell(row=grade_row, column=4, value=f'=IF(D{total_row}>=85,"A级-优先上架",IF(D{total_row}>=70,"B级-可上架",IF(D{total_row}>=60,"C级-待观察","D级-淘汰")))').font = Font(name='微软雅黑', size=12, bold=True)
    
    for col in range(1, 6):
        ws1.cell(row=total_row, column=col).border = thin_border
        ws1.cell(row=grade_row, column=col).border = thin_border
        ws1.cell(row=total_row, column=col).alignment = center_align
        ws1.cell(row=grade_row, column=col).alignment = center_align
    
    # 决策说明
    decision_row = grade_row + 2
    ws1.merge_cells(f'A{decision_row}:E{decision_row}')
    ws1[f'A{decision_row}'] = '决策规则：A级(≥85分)优先上架 | B级(70-84分)可上架 | C级(60-69分)待观察 | D级(<60分)淘汰'
    ws1[f'A{decision_row}'].font = Font(name='微软雅黑', size=10, italic=True, color='C00000')
    ws1[f'A{decision_row}'].alignment = center_align
    
    # ========== Sheet 2: 全成本利润计算器 ==========
    ws2 = wb.create_sheet("全成本利润计算器")
    
    ws2.merge_cells('A1:D1')
    ws2['A1'] = '全成本利润率计算器'
    ws2['A1'].font = Font(name='微软雅黑', size=14, bold=True, color='FFFFFF')
    ws2['A1'].fill = PatternFill(start_color='1F3864', end_color='1F3864', fill_type='solid')
    ws2['A1'].alignment = center_align
    ws2.row_dimensions[1].height = 30
    
    calc_items = [
        ('售价(USD)', 39.99, '目标售价'),
        ('汇率(USD→CNY)', 7.2, '当前汇率'),
        ('采购价(CNY)', 40.88, '1688采购价'),
        ('产品重量(kg)', 2.5, '用于计算国际物流'),
        ('物流单价(CNY/kg)', 50, '国际专线物流单价（首重+续重折算）'),
        ('平台费率(%)', 2.9, 'Stripe支付手续费'),
        ('平台固定费(CNY)', 2.16, 'Stripe每笔固定费($0.30×7.2)'),
        ('营销费率(%)', 15, 'Facebook/Google广告占售价比'),
        ('其他费用(CNY)', 5, '退货损耗/客服/包装等'),
    ]
    
    for i, (item, value, note) in enumerate(calc_items):
        row = i + 3
        ws2.cell(row=row, column=1, value=item).font = normal_font
        ws2.cell(row=row, column=2, value=value).font = normal_font
        ws2.cell(row=row, column=3, value=note).font = Font(name='微软雅黑', size=9, color='666666')
        
        for col in range(1, 4):
            ws2.cell(row=row, column=col).border = thin_border
            ws2.cell(row=row, column=col).alignment = center_align
    
    # 计算结果
    result_start = len(calc_items) + 4
    results = [
        ('售价(CNY)', '=B3*B4', '售价×汇率'),
        ('国际物流费(CNY)', '=B6*B7', '重量×物流单价'),
        ('平台费(CNY)', '=B11*B8/100+B9', '售价×费率+固定费'),
        ('营销费(CNY)', '=B11*B10/100', '售价×营销费率'),
        ('总成本(CNY)', '=B5+B13+B14+B15+B12', '采购+物流+平台+营销+其他'),
        ('利润(CNY)', '=B11-B16', '售价-总成本'),
        ('全成本利润率(%)', '=B17/B11*100', '利润/售价×100%'),
    ]
    
    ws2.merge_cells(f'A{result_start-1}:C{result_start-1}')
    ws2[f'A{result_start-1}'] = '计算结果'
    ws2[f'A{result_start-1}'].font = header_font
    ws2[f'A{result_start-1}'].fill = header_fill
    ws2[f'A{result_start-1}'].alignment = center_align
    
    for i, (item, formula, note) in enumerate(results):
        row = result_start + i
        ws2.cell(row=row, column=1, value=item).font = Font(name='微软雅黑', size=10, bold=True)
        ws2.cell(row=row, column=2, value=formula).font = Font(name='微软雅黑', size=11, bold=True, color='C00000')
        ws2.cell(row=row, column=3, value=note).font = Font(name='微软雅黑', size=9, color='666666')
        
        for col in range(1, 4):
            ws2.cell(row=row, column=col).border = thin_border
            ws2.cell(row=row, column=col).alignment = center_align
    
    # 利润率评级
    grade_row2 = result_start + len(results) + 1
    ws2.cell(row=grade_row2, column=1, value='利润率评级').font = Font(name='微软雅黑', size=11, bold=True)
    ws2.cell(row=grade_row2, column=2, value=f'=IF(B{result_start+6}>=70,"优秀(>70%)",IF(B{result_start+6}>=60,"良好(60-70%)",IF(B{result_start+6}>=50,"一般(50-60%)",IF(B{result_start+6}>=40,"偏低(40-50%)","偏低(<40%)"))))').font = Font(name='微软雅黑', size=11, bold=True)
    
    ws2.column_dimensions['A'].width = 20
    ws2.column_dimensions['B'].width = 15
    ws2.column_dimensions['C'].width = 35
    
    # ========== Sheet 3: 评分标准参考 ==========
    ws3 = wb.create_sheet("评分标准参考")
    
    ws3.merge_cells('A1:C1')
    ws3['A1'] = '11维度评分标准参考'
    ws3['A1'].font = Font(name='微软雅黑', size=14, bold=True, color='FFFFFF')
    ws3['A1'].fill = PatternFill(start_color='1F3864', end_color='1F3864', fill_type='solid')
    ws3['A1'].alignment = center_align
    ws3.row_dimensions[1].height = 30
    
    ref_headers = ['评分区间', '等级', '标准说明']
    for col, header in enumerate(ref_headers, 1):
        cell = ws3.cell(row=2, column=col, value=header)
        cell.font = sub_header_font
        cell.fill = sub_header_fill
        cell.alignment = center_align
        cell.border = thin_border
    
    ref_data = [
        ('90-100', '优秀', '各项指标达到行业顶尖水平'),
        ('80-89', '良好', '各项指标优于行业平均水平'),
        ('70-79', '中等', '各项指标达到行业平均水平'),
        ('60-69', '及格', '各项指标基本达标，但有明显短板'),
        ('<60', '不及格', '存在严重问题，不建议选品'),
    ]
    
    for i, (score, grade, note) in enumerate(ref_data):
        row = i + 3
        ws3.cell(row=row, column=1, value=score).font = normal_font
        ws3.cell(row=row, column=2, value=grade).font = normal_font
        ws3.cell(row=row, column=3, value=note).font = normal_font
        
        for col in range(1, 4):
            ws3.cell(row=row, column=col).border = thin_border
            ws3.cell(row=row, column=col).alignment = center_align
    
    ws3.column_dimensions['A'].width = 15
    ws3.column_dimensions['B'].width = 10
    ws3.column_dimensions['C'].width = 50
    
    # 保存文件
    output_path = r'E:\AI\nuotao-ai-os\docs\选品评分模板_V2.0.xlsx'
    wb.save(output_path)
    print(f"选品评分模板已生成: {output_path}")
    return output_path

if __name__ == '__main__':
    create_selection_template()
