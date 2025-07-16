# poker_crop_tool

User crop poker region tools, output XML and JSON according to the format used by OBS and poker inference program

Note :  Step1_get_poker_annotation.py 即為標註工具，可產出用於推論端的xml與模糊卡背的json  
如需使用Step2與Step 3，需手動更改一些參數名稱，如檔名  

### Build : 

conda create -n poker_crop_build_test python=3.10.12 -y  
conda activate poker_crop_build_test  
pip install -r requirements.txt  

smoke test :  python Step1_get_poker_annotation.py  => OK  

### 打包成exe的步驟  
pip install pyinstaller  
pyinstaller --clean --noconfirm --console --name poker_crop_tool Step1_get_poker_annotation.py  