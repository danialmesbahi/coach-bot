"""Product configuration shared by the web editor and Telegram checkout."""
import json
import re
from urllib.parse import urlsplit

FIELDS = ('name','phone','age','gender','height','weight','allergy','restriction','supplements','goal','training_history','notes','body_photo')


def object_value(value):
    return json.loads(value) if isinstance(value,str) else value


def validate_product(body):
    if not isinstance(body,dict):
        raise ValueError('invalid_product')
    result={}
    for key,limit in (('title',100),('description',1500),('response_text',2000),('content_url',1500)):
        value=body.get(key,'')
        if not isinstance(value,str) or len(value)>limit:
            raise ValueError(key)
        result[key]=value.strip()
    if not result['title']:
        raise ValueError('title')
    for key,low,high in (('price_irr',1000,1_000_000_000),('duration_days',-1,36500),('sort_order',0,32767)):
        value=body.get(key,0)
        if type(value) is not int or not low<=value<=high:
            raise ValueError(key)
        result[key]=value
    unit=body.get('duration_unit','days')
    factors={'days':1,'weeks':7,'months':30,'years':365}
    days=result['duration_days']
    if unit not in {*factors,'lifetime','once'} or (
        unit in factors and (days<1 or days%factors[unit])
        or unit=='lifetime' and days!=0 or unit=='once' and days!=-1):
        raise ValueError('duration_days')
    result['duration_unit']=unit
    mode=body.get('delivery_mode')
    if mode not in {'manual','content','channel'}:
        raise ValueError('delivery_mode')
    result['delivery_mode']=mode
    if unit=='once' and mode!='content':
        raise ValueError('once_content_only')
    fields=body.get('form_fields',[])
    if not isinstance(fields,list) or len(fields)>len(FIELDS) or any(field not in FIELDS for field in fields):
        raise ValueError('form_fields')
    result['form_fields']=[field for field in FIELDS if field in fields]
    questions=body.get('questions',[])
    if not isinstance(questions,list) or len(questions)>10 or any(not isinstance(q,str) or not 1<=len(q.strip())<=200 for q in questions):
        raise ValueError('questions')
    result['questions']=[q.strip() for q in questions]
    urls=body.get('content_urls', [result['content_url']] if result['content_url'] else [])
    if not isinstance(urls,list) or len(urls)>20 or any(not isinstance(url,str) or not 1<=len(url)<=1500 for url in urls):
        raise ValueError('content_urls')
    urls=[url.strip() for url in urls]
    if len(set(urls))!=len(urls):
        raise ValueError('content_urls')
    for url in urls:
        parts=urlsplit(url)
        if parts.scheme!='https' or not parts.hostname or parts.username or parts.password or re.search(r'\s',url):
            raise ValueError('content_urls')
    result['content_urls']=urls
    result['content_url']=urls[0] if urls else ''
    for key in ('asset_id','channel_id'):
        value=body.get(key)
        if value is not None and (type(value) is not int or (key=='asset_id' and value<1) or (key=='channel_id' and value>=0) or abs(value)>2**52):
            raise ValueError(key)
        result[key]=value
    assets=body.get('asset_ids',[result['asset_id']] if result['asset_id'] else [])
    if not isinstance(assets,list) or any(type(i) is not int or not 0<i<2**52 for i in assets) or len(set(assets))!=len(assets):
        raise ValueError('asset_ids')
    result['asset_ids']=assets
    result['asset_id']=assets[0] if assets else None
    if mode=='channel' and not result['channel_id']:
        raise ValueError('channel_id')
    if mode=='content' and not any(result[key] for key in ('response_text','content_urls','asset_id')):
        raise ValueError('content_required')
    if type(body.get('active')) is not bool:
        raise ValueError('active')
    result['active']=body['active']
    return result


def purchase_terms(product):
    return {key:object_value(product[key]) if key in ('form_fields','questions','content_urls') else product.get(key)
            for key in ('title','description','duration_days','duration_unit','delivery_mode','form_fields','questions','response_text','content_url','content_urls','channel_id','asset_id','asset_ids') if key in product}


def duration_label(product):
    days=product.get('duration_days',30)
    if days==0: return 'دائمی'
    if days==-1: return 'یک‌بار مصرف'
    unit=product.get('duration_unit','days')
    factor,label={'days':(1,'روز'),'weeks':(7,'هفته'),'months':(30,'ماه'),'years':(365,'سال')}.get(unit,(1,'روز'))
    return f'{days//factor} {label}'
