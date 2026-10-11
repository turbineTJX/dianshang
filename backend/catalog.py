"""Business operations are independent of vendor names, models and protocols."""

def item(id, name, group, capability, kind='image', price=10, minimum=1, maximum=6, description=''):
    return dict(id=id, name=name, group=group, capability=capability, kind=kind,
                price=price, min_assets=minimum, max_assets=maximum, description=description)

OPERATIONS = [
    item('text_to_image', '创意生图', 'image', 'image.generate', minimum=0, maximum=0, description='用文字描述生成商品背景或创意素材'),
    item('product_scene', '商品场景图', 'image', 'image.edit', description='保留商品主体，为商品创建新的展示场景'),
    item('product_suite', '商品套图', 'image', 'image.edit', price=10, description='主图、场景、细节、卖点图组成一套商品视觉'),
    item('white_background', '商品白底图', 'image', 'image.cutout', price=5, maximum=1, description='识别商品主体并生成干净的白底图片'),
    item('product_replace', '商品替换', 'image', 'image.edit', minimum=2, description='用商品原图替换参考场景里的商品'),
    item('smart_edit', '智能修图', 'image', 'image.edit', description='通过文字描述修改图片中的内容'),
    item('recolor', '一键换色', 'image', 'image.edit', description='调整商品颜色，保留材质和结构'),
    item('inpaint', '局部重绘', 'image', 'image.edit', description='上传蒙版或用描述指定需要修改的区域'),
    item('erase', '局部消除', 'image', 'image.edit', description='消除图片中的指定元素'),
    item('outpaint', '智能扩图', 'image', 'image.edit', description='扩展图片画面，适配不同展示比例'),
    item('cutout', '精细抠图', 'image', 'image.cutout', price=5, maximum=1, description='生成透明背景的主体图片'),
    item('upscale', '高清放大', 'image', 'image.upscale', price=5, maximum=1, description='提升图片分辨率和清晰度'),
    item('image_translate', '图片翻译', 'image', 'image.translate', description='转换图片里的文字语言和版式'),
    item('pattern_extract', '印花提取', 'image', 'image.edit', description='从服装或商品图片中提取印花图案'),
    item('local_design', '裁剪与排版', 'image', 'local.image', price=0, maximum=1, description='本地完成尺寸调整、文字排版和水印，无需模型'),
    item('tryon', 'AI 模特穿衣', 'model', 'model.tryon', minimum=2, maximum=3, price=15, description='服装平铺图与模特图组合生成试穿效果'),
    item('mannequin', '人台换模特', 'model', 'image.edit', price=15, description='把人台展示转换为模特展示'),
    item('model_replace', '真人换模特', 'model', 'image.edit', price=15, description='参考目标模特形象，调整展示人物'),
    item('model_scene', '模特换场景', 'model', 'image.edit', price=15, description='保留服装展示，调整模特所在场景'),
    item('model_pose', '姿势裂变', 'model', 'image.edit', price=15, description='根据参考姿势生成新的服装展示图'),
    item('accessory', 'AI 穿戴', 'model', 'image.edit', minimum=2, price=15, description='为模特添加配饰、鞋包等商品'),
    item('clothing_suite', '服装套图', 'model', 'image.edit', price=15, description='模特图、细节图、场景图的组合生产'),
    item('image_to_video', '商品图转视频', 'video', 'video.generate', 'video', 60, maximum=2, description='让商品图片生成动态展示短片'),
    item('model_video', '模特展示视频', 'video', 'video.generate', 'video', 60, maximum=2, description='从模特展示图生成动作与运镜视频'),
    item('first_last_video', '首尾帧视频', 'video', 'video.generate', 'video', 60, minimum=2, maximum=2, description='使用首帧与尾帧控制视频画面变化'),
    item('text_to_video', '文生视频', 'video', 'video.generate', 'video', 60, minimum=0, maximum=0, description='用文字描述生成商品或品牌创意短片'),
    item('talking_video', '带货口播', 'video', 'video.avatar', 'video', 80, maximum=2, description='模特素材与口播文案组合为讲解视频'),
    item('video_reference', '参考视频创作', 'video', 'video.reference', 'video', 80, description='参考视频结构与商品资料创作新的视频'),
    item('video_edit', '视频编辑', 'video', 'video.edit', 'video', 40, description='通过指令调整已有视频内容'),
    item('video_translate', '视频翻译', 'video', 'video.translate', 'video', 40, description='翻译视频的配音与字幕'),
]
BY_ID = {op['id']: op for op in OPERATIONS}
CAPABILITIES = sorted({op['capability'] for op in OPERATIONS if op['capability'] != 'local.image'} | {'agent.plan', 'link.import'})
SUITE_ROLES = [('主图', '干净的商品主图'), ('场景图', '真实使用场景图'), ('细节图', '展示商品真实细节'), ('卖点图', '根据商品资料突出卖点')]


def operation_with_price(operation_id):
    from . import db
    import json
    operation = dict(BY_ID[operation_id])
    row = db.one("SELECT value FROM settings WHERE key='prices'")
    if row and operation_id != 'local_design':
        operation['price'] = json.loads(row['value']).get(operation_id, operation['price'])
    return operation
