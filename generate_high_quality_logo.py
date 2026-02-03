from PIL import Image, ImageDraw
import os
import math

def create_high_quality_logo():
    # 创建高分辨率画布
    size = 2048
    img = Image.new('RGBA', (size, size), color=(255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    
    # 更深的蓝色渐变
    blue_top = (0, 70, 230)     # 深蓝色
    blue_bottom = (30, 160, 255) # 中蓝色
    
    # 居中参数 - 增大A字母
    center_x, center_y = size // 2, size // 2
    letter_height = size * 0.8   # 增大高度
    letter_width = size * 0.7    # 增大宽度
    
    # A字母轮廓点 - 重新设计更粗壮的A
    # 左侧点
    left_x1 = center_x - letter_width * 0.35
    left_x2 = center_x - letter_width * 0.15
    
    # 右侧点
    right_x1 = center_x + letter_width * 0.15
    right_x2 = center_x + letter_width * 0.35
    
    # 上下位置
    top_y = center_y - letter_height * 0.4
    bottom_y = center_y + letter_height * 0.4
    
    # 使用多边形而不是线条填充A字母
    points = [
        (left_x1, bottom_y),                     # 左下
        (center_x - letter_width * 0.1, top_y),  # 左上
        (center_x + letter_width * 0.1, top_y),  # 右上
        (right_x2, bottom_y),                    # 右下
        (right_x1, bottom_y),                    # 右下内
        (center_x, top_y + letter_height * 0.25),# 右中
        (left_x2, bottom_y)                      # 左下内
    ]
    
    # 绘制A字母 - 直接使用渐变多边形
    for y in range(int(top_y), int(bottom_y) + 1):
        # 计算渐变比例
        ratio = (y - top_y) / (bottom_y - top_y)
        color = (
            int(blue_top[0] * (1-ratio) + blue_bottom[0] * ratio),
            int(blue_top[1] * (1-ratio) + blue_bottom[1] * ratio),
            int(blue_top[2] * (1-ratio) + blue_bottom[2] * ratio)
        )
        
        # 计算该y位置的左右交点
        intersections = []
        
        # 检查与每个边的交点
        for i in range(len(points)):
            p1 = points[i]
            p2 = points[(i+1) % len(points)]
            
            # 如果线段跨越当前y值
            if (p1[1] <= y <= p2[1]) or (p2[1] <= y <= p1[1]):
                # 计算交点的x坐标
                if p1[1] == p2[1]:  # 水平线
                    if p1[0] > p2[0]:
                        intersections.append(p2[0])
                        intersections.append(p1[0])
                    else:
                        intersections.append(p1[0])
                        intersections.append(p2[0])
                else:  # 斜线
                    x = p1[0] + (y - p1[1]) * (p2[0] - p1[0]) / (p2[1] - p1[1])
                    intersections.append(x)
        
        # 按x坐标排序交点
        intersections.sort()
        
        # 绘制水平线段填充多边形
        for i in range(0, len(intersections), 2):
            if i+1 < len(intersections):
                x1 = int(intersections[i])
                x2 = int(intersections[i+1])
                
                # 添加中间的横杠缺口
                middle_y = center_y - letter_height * 0.05
                if abs(y - middle_y) < letter_height * 0.05:
                    middle_left = center_x - letter_width * 0.2
                    middle_right = center_x + letter_width * 0.2
                    
                    # 绘制左半部分
                    if x1 < middle_left and x2 > middle_left:
                        draw.line([(x1, y), (middle_left, y)], fill=color, width=8)
                    elif x1 >= middle_right:
                        draw.line([(x1, y), (x2, y)], fill=color, width=8)
                    
                    # 绘制右半部分
                    if x1 < middle_right and x2 > middle_right:
                        draw.line([(middle_right, y), (x2, y)], fill=color, width=8)
                    elif x1 < middle_left and x2 <= middle_left:
                        draw.line([(x1, y), (x2, y)], fill=color, width=8)
                else:
                    # 绘制常规线段
                    draw.line([(x1, y), (x2, y)], fill=color, width=8)
    
    # 绘制更明显的音频波形
    wave_count = 40
    wave_width = size * 0.9
    wave_max_height = letter_height * 0.3
    wave_x_start = center_x - wave_width / 2
    
    for i in range(wave_count):
        x = wave_x_start + i * (wave_width / (wave_count - 1))
        
        # 波形高度 - 使用正弦波形状让波形更自然
        rel_pos = (x - wave_x_start) / wave_width
        phase = rel_pos * math.pi * 2  # 完整的正弦周期
        
        # 使波形从中间向两边递减
        dist_from_center = abs((x - center_x) / (wave_width / 2))
        amplitude = max(0, 1 - dist_from_center * 1.2)
        
        # 波形高度，中间部分更高
        height = wave_max_height * amplitude
        
        # 波形宽度，保持粗一些
        thickness = max(6, int(15 * amplitude))
        
        # 波形颜色 - 使用相同的渐变
        if x < center_x:
            ratio = 0.2  # 左侧更深色
        else:
            ratio = 0.2 + 0.8 * ((x - center_x) / (wave_width / 2))
        
        wave_color = (
            int(blue_top[0] * (1-ratio) + blue_bottom[0] * ratio),
            int(blue_top[1] * (1-ratio) + blue_bottom[1] * ratio),
            int(blue_top[2] * (1-ratio) + blue_bottom[2] * ratio)
        )
        
        # 不绘制与A字母重叠的部分
        if (x < left_x1 - 20) or (x > right_x2 + 20):
            draw.line(
                [(x, center_y - height), (x, center_y + height)],
                fill=wave_color,
                width=thickness
            )
    
    # 确保logo目录存在
    if not os.path.exists("logo"):
        os.makedirs("logo")
    
    # 保存PNG
    img.save("logo/AcouTest.png")
    
    # 创建正方形图标
    icon_size = 512
    icon_img = img.resize((icon_size, icon_size), Image.LANCZOS)
    icon_img.save("logo/AcouTest_icon.png")
    
    print("Logo已生成! 路径: logo/AcouTest.png")

if __name__ == "__main__":
    create_high_quality_logo() 