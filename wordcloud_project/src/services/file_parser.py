"""File parser module - handles CSV/Excel file upload and parsing."""

import os
import json
import pandas as pd
from io import StringIO


def parse_csv_with_encoding(file_content, filename=None):
    """
    Try multiple encodings to parse CSV file.
    
    Args:
        file_content: Raw file bytes
        filename: Original filename for logging
        
    Returns:
        tuple: (DataFrame, encoding) or (None, None)
    """
    encodings_to_try = ['utf-8', 'utf-8-sig', 'cp949', 'euc-kr', 'cp932', 'shift-jis', 'latin1']
    separators = [',', ';', '\t', '|']
    
    for encoding in encodings_to_try:
        try:
            for sep in separators:
                try:
                    df = pd.read_csv(StringIO(file_content.decode(encoding)), sep=sep, encoding='utf-8')
                    if not df.empty and len(df.columns) > 0:
                        return df, encoding
                except:
                    continue
        except:
            continue
    
    return None, None


def extract_column_info(df):
    """
    Extract column metadata from DataFrame.
    
    Args:
        df: pandas DataFrame
        
    Returns:
        list: Column info list with name, type, sample
    """
    columns = []
    for col in df.columns:
        sample_value = None
        for val in df[col].dropna():
            if pd.notna(val):
                sample_value = str(val)[:50]
                break
        
        dtype = str(df[col].dtype)
        if dtype == 'object':
            col_type = '텍스트'
        elif 'int' in dtype:
            col_type = '정수'
        elif 'float' in dtype:
            col_type = '실수'
        elif 'datetime' in dtype:
            col_type = '날짜'
        else:
            col_type = '기타'
        
        columns.append({
            'name': str(col),
            'type': col_type,
            'sample': sample_value or 'N/A'
        })
    
    return columns


def normalize_dataframe(df):
    """
    Normalize DataFrame encoding to UTF-8.
    
    Args:
        df: pandas DataFrame
        
    Returns:
        pandas DataFrame
    """
    for col in df.columns:
        if df[col].dtype == 'object':
            df[col] = df[col].apply(
                lambda x: str(x).encode('utf-8', 'replace').decode('utf-8') if pd.notna(x) else x
            )
    return df


def parse_uploaded_file(file):
    """
    Parse uploaded file (CSV or Excel).
    
    Args:
        file: Flask file object
        
    Returns:
        tuple: (dict result, status_code)
            - result: {'filename', 'rows', 'columns', 'preview_data', 'preview_rows'}
            - status_code: 200 or error code
    """
    if not file or file.filename == '':
        return {'error': '파일이 선택되지 않았습니다.'}, 400
    
    filename = file.filename.lower()
    
    # Check file extension
    if not (filename.endswith('.csv') or filename.endswith(('.xlsx', '.xls'))):
        return {'error': '지원되지 않는 파일 형식입니다. CSV 또는 Excel 파일만 업로드 가능합니다.'}, 400
    
    # Check file size (50MB limit)
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    if file_size > 50 * 1024 * 1024:
        return {'error': '파일 크기가 50MB를 초과합니다.'}, 400
    
    try:
        df = None
        
        if filename.endswith('.csv'):
            file_content = file.read()
            if not file_content:
                return {'error': '빈 파일입니다.'}, 400
            
            df, encoding = parse_csv_with_encoding(file_content, filename)
            if df is None:
                return {'error': 'CSV 파일을 읽을 수 없습니다. UTF-8, CP949, EUC-KR 등 표준 인코딩으로 저장된 파일인지 확인해주세요.'}, 400
                
        elif filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(file)
        
        if df is None or df.empty:
            return {'error': '파일에 데이터가 없습니다.'}, 400
        
        if len(df.columns) == 0:
            return {'error': '파일에 열이 없습니다.'}, 400
        
        # Normalize encoding
        df = normalize_dataframe(df)
        
        # Extract column info
        columns = extract_column_info(df)
        
        # Get preview data
        preview_rows = df.head(10).replace({float('nan'): None, float('inf'): None, float('-inf'): None}).to_dict('records')
        
        return {
            'filename': file.filename,
            'rows': len(df),
            'columns': columns,
            'preview_data': preview_rows,
            'preview_rows': preview_rows
        }, 200
        
    except Exception as e:
        return {'error': f'파일 처리 중 오류가 발생했습니다: {str(e)}'}, 500


def parse_csv_file(file):
    """
    Parse CSV file for analysis.
    
    Args:
        file: Flask file object
        
    Returns:
        tuple: (dict result, status_code)
    """
    if not file or file.filename == '':
        return {'error': '파일이 선택되지 않았습니다.'}, 400
    
    if not file.filename.endswith('.csv'):
        return {'error': 'CSV 파일만 업로드 가능합니다.'}, 400
    
    try:
        file_content = file.read()
        if not file_content:
            return {'error': '빈 파일입니다.'}, 400
        
        df, encoding = parse_csv_with_encoding(file_content, file.filename)
        if df is None:
            return {'error': '지원되지 않는 파일 형식입니다. CSV 파일을 확인하고 UTF-8, CP949, EUC-KR 등 표준 인코딩으로 저장해주세요.'}, 400
        
        headers = df.columns.tolist()
        rows = df.head(10).values.tolist()
        
        return {
            'headers': headers,
            'rows': rows,
            'encoding': encoding
        }, 200
        
    except Exception as e:
        return {'error': f'파일 처리 실패: {str(e)}'}, 500