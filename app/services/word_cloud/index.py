from wordcloud import WordCloud
from io import BytesIO
import os
import glob
from pathlib import Path
import random
import numpy as np
from PIL import Image, ImageDraw


def generate_word_cloud(keywords: list, font: int = None, color: int = None, mask: int = None) -> BytesIO:
    """
    키워드 리스트로부터 워드 클라우드 이미지를 생성합니다.

    Args:
        keywords: [{"keyword": "키워드", "raw_weight": 7.2}, ...] 형식의 키워드 리스트
        font: 폰트 인덱스 (0-6, None이면 랜덤)
        color: 색상 테마 인덱스 (0-19, None이면 랜덤)
        mask: 마스크 인덱스 (None이면 직사각형)

    Returns:
        BytesIO: 워드 클라우드 이미지의 바이트 스트림
    """
    try:
        # 키워드 리스트를 frequency dictionary로 변환
        # wordcloud는 {word: frequency} 형식을 받음
        frequencies = {}
        for item in keywords:
            keyword = item.get("keyword", "")
            raw_weight = item.get("raw_weight", 1.0)
            if keyword:
                frequencies[keyword] = float(raw_weight)

        if not frequencies:
            raise ValueError("키워드 데이터가 비어있습니다.")

        # 가중치 내림차순으로 정렬 (큰 단어가 중앙에 먼저 배치되도록)
        frequencies = dict(sorted(frequencies.items(), key=lambda x: x[1], reverse=True))

        print(f"키워드 정렬 순서 (상위 5개): {list(frequencies.keys())[:5]}")

        # 키워드 개수에 따라 relative_scaling 동적 조절
        keyword_count = len(frequencies)
        relative_scaling = min(keyword_count / 100, 1.0)  # 최대 1.0
        print(f"키워드 개수: {keyword_count}, relative_scaling: {relative_scaling:.3f}")

        # 한글 폰트 경로 설정
        font_path = get_korean_font_path(font)

        if not font_path:
            raise ValueError("한글 폰트를 찾을 수 없습니다. fonts/ 디렉토리에 폰트를 설치해주세요.")

        # 폰트 파일 존재 확인
        if not os.path.exists(font_path):
            raise ValueError(f"폰트 파일이 존재하지 않습니다: {font_path}")

        # 색상 테마 선택
        colormap = get_colormap(color)

        print(f"워드 클라우드 생성 - 폰트: {os.path.basename(font_path)}, 색상: {colormap}")

        # 워드 클라우드 생성
        wc_params = {
            'background_color': 'white',
            'font_path': font_path,
            'relative_scaling': relative_scaling,
            'min_font_size': 1,
            'max_font_size': 100,
            'max_words': 500,
            'colormap': colormap,
            'prefer_horizontal': 0.9,
            'margin': 10
        }

        # 마스크가 있으면 mask 사용, 없으면 width/height 사용
        if mask is not None:
            wc_params['mask'] = get_mask(mask)
            wc_params['contour_width'] = 0
        else:
            wc_params['width'] = 580
            wc_params['height'] = 520

        wordcloud = WordCloud(**wc_params).generate_from_frequencies(frequencies)

        # 이미지를 바이트 스트림으로 변환
        img_buffer = BytesIO()
        wordcloud.to_image().save(img_buffer, format='PNG')
        img_buffer.seek(0)

        return img_buffer

    except Exception as e:
        print(f"워드 클라우드 생성 중 오류 발생: {e}")
        raise


def get_korean_font_path(font_index: int = None) -> str:
    """
    프로젝트 fonts 디렉토리에서 한글 폰트 경로를 찾습니다.

    Args:
        font_index: 폰트 인덱스 (0부터 시작). None이면 랜덤 선택

    Returns:
        str: 한글 폰트 파일 경로
    """
    # 프로젝트 루트의 fonts 디렉토리
    current_dir = Path(__file__).resolve().parent
    project_root = current_dir.parent.parent.parent
    fonts_dir = project_root / "fonts"

    if not fonts_dir.exists():
        print("❌ fonts/ 디렉토리가 존재하지 않습니다.")
        return None

    # 디렉토리 내 모든 폰트 파일 찾기
    all_fonts = sorted(list(fonts_dir.glob("*.ttf")) + list(fonts_dir.glob("*.otf")))

    if not all_fonts:
        print("❌ fonts/ 디렉토리에 폰트 파일이 없습니다.")
        return None

    # 폰트 선택
    if font_index is None:
        # 랜덤 선택
        selected_font = random.choice(all_fonts)
        selected_index = all_fonts.index(selected_font)
        print(f"🎲 랜덤 선택: [{selected_index}] {selected_font.name}")
    else:
        # 인덱스로 선택
        if 0 <= font_index < len(all_fonts):
            selected_font = all_fonts[font_index]
            print(f"✅ 선택된 폰트: [{font_index}] {selected_font.name}")
        else:
            print(f"⚠️ 잘못된 폰트 인덱스: {font_index} (0-{len(all_fonts) - 1} 사용 가능)")
            # fallback to random
            selected_font = random.choice(all_fonts)
            selected_index = all_fonts.index(selected_font)
            print(f"🎲 랜덤 선택으로 대체: [{selected_index}] {selected_font.name}")

    return str(selected_font)


def get_colormap(colormap_index: int = None) -> str:
    """
    워드 클라우드 색상 테마를 선택합니다.

    Args:
        colormap_index: 색상 테마 인덱스 (0-19). None이면 랜덤 선택

    Returns:
        str: matplotlib colormap 이름
    """
    # 사용 가능한 색상 테마 목록
    available_colormaps = [
        'viridis',  # 보라-청록-노랑
        'plasma',  # 보라-분홍-노랑
        'inferno',  # 검정-보라-주황-노랑
        'magma',  # 검정-보라-분홍-흰색
        'cividis',  # 파랑-노랑 (색맹 친화)
        'twilight',  # 핑크-보라-파랑
        'rainbow',  # 무지개
        'cool',  # 청록-보라
        'hot',  # 검정-빨강-노랑-흰색
        'spring',  # 자홍-노랑
        'summer',  # 초록-노랑
        'autumn',  # 빨강-주황-노랑
        'winter',  # 파랑-초록
        'Blues',  # 파랑 계열
        'Greens',  # 초록 계열
        'Oranges',  # 주황 계열
        'Reds',  # 빨강 계열
        'Purples',  # 보라 계열
        'PuBuGn',  # 보라-파랑-초록
        'RdYlBu',  # 빨강-노랑-파랑
    ]

    if colormap_index is None:
        # 랜덤 선택
        selected = random.choice(available_colormaps)
        selected_index = available_colormaps.index(selected)
        print(f"🎨 랜덤 색상: [{selected_index}] {selected}")
        return selected
    else:
        # 인덱스로 선택
        if 0 <= colormap_index < len(available_colormaps):
            selected = available_colormaps[colormap_index]
            print(f"✅ 선택된 색상: [{colormap_index}] {selected}")
            return selected
        else:
            # 잘못된 인덱스면 랜덤
            print(f"⚠️ 잘못된 색상 인덱스: {colormap_index} (0-{len(available_colormaps) - 1} 사용 가능)")
            selected = random.choice(available_colormaps)
            selected_index = available_colormaps.index(selected)
            print(f"🎨 랜덤 색상으로 대체: [{selected_index}] {selected}")
            return selected


def get_mask(mask: int = None) -> str:
    # 기능 미구현
    return ''
