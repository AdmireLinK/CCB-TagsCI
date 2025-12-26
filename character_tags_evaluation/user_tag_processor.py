from pymongo import MongoClient
from typing import Dict, List, Any
import json
import os


class UserTagProcessor:
    def __init__(self, mongo_uri: str = None, db_name: str = 'tags'):
        if mongo_uri is None:
            mongo_uri = os.environ.get('MONGODB_URI')
        self.mongo_uri = mongo_uri
        self.db_name = db_name
        self.client = None
        self.db = None

        self.conv = {
            '茶色瞳': '棕瞳',
            '中二': '中二病',
            '单马尾': '马尾',
            '渐变发': '渐变色发',
            '白发': '银发',
            'tv': 'TV',
            '偶像': '偶像(萌属性)',
        }

        self.hair_color_attr = [
            "黑发",
            "金发",
            "蓝发",
            "棕发",
            "银发",
            "红发",
            "紫发",
            "橙发",
            "绿发",
            "粉发",
        ]

        self.eye_color_attr = [
            "黑瞳",
            "金瞳",
            "蓝瞳",
            "棕瞳",
            "灰瞳",
            "红瞳",
            "紫瞳",
            "橙瞳",
            "绿瞳",
            "粉瞳",
            "白瞳",
        ]

    def connect(self):
        if self.client is None:
            self.client = MongoClient(self.mongo_uri)
            self.db = self.client[self.db_name]

    def close(self):
        if self.client is not None:
            self.client.close()
            self.client = None
            self.db = None

    def load_user_tags_from_mongo(self) -> Dict[str, Dict[str, int]]:
        self.connect()
        collection = self.db['character_tags']
        
        user_char_tags_raw = collection.find()
        
        user_char_tags = {}
        for i in user_char_tags_raw:
            id = str(i['_id'])
            tagCounts = i['tagCounts']
            tags = {}
            for k, v in tagCounts.items():
                if k in self.conv:
                    k = self.conv[k]
                tags[k] = v
            user_char_tags[id] = tags
        
        self.close()
        return user_char_tags

    def merge_user(self, bgmid: str, tags: List[str], user_tags: Dict[str, int]) -> List[str]:
        multicolor_hair = False

        merged_tags = tags + list(
            map(lambda x: x[0], filter(lambda x: x[1] > 1, user_tags.items()))
        )
        if (
            '双色发' in merged_tags
            or '渐变色发' in merged_tags
            or '彩虹发' in merged_tags
            or '多色发' in merged_tags
            or '阴阳发' in merged_tags
            or '挑染' in merged_tags
            or '内层挑染' in merged_tags
            or '变发色' in merged_tags
        ):
            multicolor_hair = True

        multicolor_eye = False
        if '异色瞳' in merged_tags or '渐变瞳' in merged_tags or '彩虹瞳' in merged_tags:
            multicolor_eye = True

        d = {}
        d_hair = {}
        d_eye = {}
        for tag in tags:
            if tag in self.hair_color_attr:
                d_hair[tag] = 4
            elif tag in self.eye_color_attr:
                d_eye[tag] = 4
            else:
                d[tag] = 4

        original_hair = list(d_hair.keys())
        original_eye = list(d_eye.keys())

        for tag, count in user_tags.items():
            if count <= 1:
                continue
            if tag in self.hair_color_attr:
                d_hair[tag] = d_hair.get(tag, 0) + count
            elif tag in self.eye_color_attr:
                d_eye[tag] = d_eye.get(tag, 0) + count
            else:
                d[tag] = d.get(tag, 0) + count

        if ('长发' in d or '长直' in d or '黑长直' in d) and '短发' in d:
            lmax = max(d.get('长发', 0), d.get('长直', 0), d.get('黑长直', 0))
            smax = d.get('短发', 0)
            if lmax == smax:
                pass
            elif lmax > smax:
                del d['短发']
            else:
                if '长发' in d:
                    del d['长发']
                if '长直' in d:
                    del d['长直']
                if '黑长直' in d:
                    del d['黑长直']

        ret = []
        for tag, count in d.items():
            if count >= 2:
                ret.append(tag)

        d_hair = sorted(
            filter(lambda x: x[1] > 1, list(d_hair.items())),
            key=lambda x: x[1],
            reverse=True,
        )
        d_eye = sorted(
            filter(lambda x: x[1] > 1, list(d_eye.items())),
            key=lambda x: x[1],
            reverse=True,
        )

        ret_hair = original_hair.copy()
        if multicolor_hair:
            if len(d_hair) < 2:
                pass
            elif len(d_hair) == 2:
                ret_hair = [d_hair[0][0], d_hair[1][0]]
            else:
                if d_hair[1][1] >= d_hair[2][1] * 2:
                    ret_hair = [d_hair[0][0], d_hair[1][0]]
        else:
            if len(d_hair) < 1:
                pass
            elif len(d_hair) == 1:
                ret_hair = [d_hair[0][0]]
            else:
                if d_hair[0][1] >= d_hair[1][1] * 2:
                    ret_hair = [d_hair[0][0]]

        ret_eye = original_eye.copy()
        if multicolor_eye:
            if len(d_eye) < 2:
                pass
            elif len(d_eye) == 2:
                ret_eye = [d_eye[0][0], d_eye[1][0]]
            else:
                if d_eye[1][1] >= d_eye[2][1] * 2:
                    ret_eye = [d_eye[0][0], d_eye[1][0]]
        else:
            if len(d_eye) < 1:
                pass
            elif len(d_eye) == 1:
                ret_eye = [d_eye[0][0]]
            else:
                if d_eye[0][1] >= d_eye[1][1] * 2:
                    ret_eye = [d_eye[0][0]]

        ret = ret_hair + ret_eye + ret

        return ret

    def load_id_tags_from_json(self, json_path: str = None) -> Dict[str, List[str]]:
        if json_path is None:
            json_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'outputs', 'id_tags.json')
        
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def merge_and_save_tags(self, user_tags: Dict[str, Dict[str, int]], 
                           original_tags: Dict[str, List[str]] = None,
                           output_js_path: str = None) -> Dict[str, List[str]]:
        if original_tags is None:
            original_tags = self.load_id_tags_from_json()
        
        merged_tags = {}
        for bgmid, tags in original_tags.items():
            if bgmid in user_tags:
                merged_tags[bgmid] = self.merge_user(bgmid, tags, user_tags[bgmid])
            else:
                merged_tags[bgmid] = tags
        
        if output_js_path is None:
            output_js_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'outputs', 'id_tags.js')
        
        if output_js_path is not None:
            self.save_to_js(merged_tags, output_js_path)
        
        return merged_tags

    def save_to_js(self, tags_dict: Dict[str, List[str]], output_path: str):
        with open(output_path, "w", encoding='utf-8') as f:
            f.write('export const idToTags = {\n')
            tags = []
            for k, v in tags_dict.items():
                tags.append((k, ':[' + ','.join(map(lambda x: f'"{x}"', v)) + ']'))
            tags.sort(key=lambda x: int(x[0]))
            f.write(',\n'.join(map(lambda x: str(x[0]) + x[1], tags)))
            f.write('\n};')
