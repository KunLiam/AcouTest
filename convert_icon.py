from PIL import Image
import os
import glob

try:
    print("开始转换您提供的图片为图标...")
    
    # 确保logo目录存在
    if not os.path.exists("logo"):
        os.makedirs("logo")
        print("创建logo目录")
    
    # 查找logo目录中的图片文件
    image_files = glob.glob("logo/*.png") + glob.glob("logo/*.jpg") + glob.glob("logo/*.jpeg")
    
    if not image_files:
        print("错误: 在logo目录中没有找到PNG或JPG图片")
        print("请将您的图片文件放在logo目录中，命名不限")
        exit(1)
    
    # 使用找到的第一个图片文件
    source_image = image_files[0]
    print(f"找到图片: {source_image}")
    
    # 加载图片
    img = Image.open(source_image)
    
    # 转换为RGBA模式以支持透明度
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    
    # 获取原始尺寸
    original_width, original_height = img.size
    print(f"原始图片尺寸: {original_width}x{original_height}")
    
    # 如果图片太小，放大到至少512x512
    if original_width < 512 or original_height < 512:
        scale = max(512 / original_width, 512 / original_height)
        new_width = int(original_width * scale)
        new_height = int(original_height * scale)
        img = img.resize((new_width, new_height), Image.LANCZOS)
        print(f"已放大图片至: {new_width}x{new_height}，使用高质量LANCZOS算法")
    
    # 确保图片是正方形(ICO文件最好是正方形)
    width, height = img.size
    if width != height:
        # 创建一个正方形透明画布
        size = max(width, height)
        square_img = Image.new('RGBA', (size, size), (255, 255, 255, 0))
        # 将原图粘贴到中央
        paste_x = (size - width) // 2
        paste_y = (size - height) // 2
        square_img.paste(img, (paste_x, paste_y))
        img = square_img
        print(f"已调整为正方形: {size}x{size}")
    
    # 保存为高质量PNG (用于备份)
    png_path = os.path.join("logo", "AcouTest.png")
    img.save(png_path, format="PNG")
    print(f"已保存高质量PNG: {png_path}")
    
    # 创建多种尺寸的图标 - 从大到小排序
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    ico_path = os.path.join("logo", "AcouTest.ico")
    
    # 创建各种尺寸的缩略图
    resized_images = []
    for size_tuple in sizes:
        resized = img.resize(size_tuple, Image.LANCZOS)  # 使用高质量的LANCZOS算法
        resized_images.append(resized)
    
    # 保存为ICO文件，包含多种尺寸
    resized_images[0].save(ico_path, format="ICO", sizes=sizes, append_images=resized_images[1:])
    
    print(f"高清ICO文件已成功创建: {ico_path}")
    print(f"ICO文件包含以下尺寸: {', '.join([f'{s[0]}x{s[1]}' for s in sizes])}")
    
    # 验证ICO文件是否存在
    if os.path.exists(ico_path):
        print(f"验证成功: ICO文件存在，大小为 {os.path.getsize(ico_path)/1024:.2f} KB")
    else:
        print("错误: ICO文件创建失败")

except Exception as e:
    print(f"转换图标时出错: {str(e)}")
