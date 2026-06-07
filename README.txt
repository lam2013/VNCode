=============================
		   VNCode
============================
    

giới thiệu:
	đây là phần mềm IDE được một người Việt làm và dùng GPLv3 100%

tree file:
  {parent_folder}
   | (file)
   |- run.py
   |- list_module.py
   |- fill_module.py
   |- auto_build.bat
   |- icon_VNCode.ico
   |- close.svg
   |- hover_close.svg
   |- README.txt
   |- config_VNCode.json
   |- LICENSE
 (end)
 
tính năng:
	+hỗ trợ code và chạy được những ngôn ngữ sau:
		+python
		+c
		+cpp
		+cs
		+java
		+R
		+rust
		+go
		+lua
		+batch
		+bash
		+swift
		+kotlin
		+powershell
	- thêm extension marketplace
	- hỗ trợ đa số extension
	- thêm LSP:
	    + v1.1:
			+ python
		+ v1.2:
			+ c/c++
		+ v1.3:
			+ c#
	- mini update:
		+ thêm icon languese
	v1.2:
	- update highlight tốt hơn:
		+ highlight syntax theo kiểu python:
			- hỗ trợ highlight cho format string ("{}") theo syntax kiểu python
			- highlight cho gọi functon(nếu đằng sau có "()" và trước đó có "." thì sẽ highlight màu tím function đó)
			- highlight (xám cho varible; xám tím cho function; xám cam class, struct,...) cho những varible, function,class,... chưa được gọi lần thứ hai
		+ highlight syntax theo kiểu c/c++:
			- highlight function (nếu sau đó có " <<" hay "<<" theo kiểu c++ hoặc kiểu gọi function của c thì tô màu tím cho function đó)
			- highlight varible, function,class,... (xám cho varible; xám tím cho function; xám cam class, struct,...)
	- thêm undo
	- thêm hỗ trợ LSP cho c/c++
	- hỗ trợ lsp tốt hơn(tìm syntax sau dấu chấm (theo syntax kiểu python) hay sau :: hoặc . (theo syntax kiểu c/c++))
	update v1.3:
	    major update:
		    - tự động cập nhật trạng thái file (tồn tại, đã bị xóa/đổi vị trí)
		    - cho phép lưu file khi file đó bị xóa hoặc bị đổi vị trí
		    - lorem


cách chạy:
1. chạy thủ công(nếu bạn biết sơ về command):
    -yêu cầu:
        +python v3.xx
    -chạy:
        +mở console(hoặc tương tự)
        +chạy lệnh như sau:
            python -u "{parent folder}\run.py"
2.tự động:
	- chạy file auto_build.bat để build exe
	- file exe được tạo ra nằm trong folder "dist"
    
thank for python
link tải python: https://www.python.org/downloads/

thư viện được dùng:
	+ PyQt5
	+ sys
	+ json
	+ os
	+ collections
	+ pathlib
	+ importlib.util
	+ shutil
	
nhà phát triển: VNCore lab(Nguyễn Trường Lâm)
nhà phát hành: VNCore lab(Nguyễn Trường Lâm)
email gửi yêu cầu fix bug/cho code để update: nguyenvannghia1952tg@gmail.com

***2025 Vncore lab (alias of Nguyễn Trường Lâm)***

*lưu ý: VNCode chỉ dành cho windows. chỉ chạy đc windows 8,8.1,10,11 và tất cả đều là 64-bit