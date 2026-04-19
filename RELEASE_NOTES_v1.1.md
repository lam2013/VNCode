# VNCode IDE v1.1 - Ghi Chú Phát Hành

**Ngày Phát Hành**: 15 Tháng 4, 2026  
**Phiên Bản Trước**: v1.0

---

## Giới Thiệu

VNCode IDE v1.1 là phần mềm IDE được phát triển bởi một lập trình viên Việt Nam, sử dụng 100% giấy phép GPLv3. Phiên bản này tập trung vào cải thiện giao diện người dùng và thêm các tính năng nâng cao cho trải nghiệm viết mã. VNCode hỗ trợ 16+ ngôn ngữ lập trình với khả năng chạy mã trực tiếp và tích hợp các extension marketplace.

## Tính Năng Mới

### 1. Hỗ Trợ Ngôn Ngữ Lập Trình
VNCode v1.1 hỗ trợ 16 ngôn ngữ lập trình phổ biến:
  - **Python**
  - **C / C++ / C#**
  - **Java**
  - **R**
  - **Rust**
  - **Go**
  - **Lua**
  - **Batch / Bash**
  - **Swift**
  - **Kotlin**
  - **PowerShell**
  - **Assembly**

Mỗi ngôn ngữ được tích hợp sẵn cú pháp trong IDE.

### 2. Tính Năng Extension Marketplace
- **Thêm mới**: Tích hợp marketplace extension cho phép người dùng cài đặt và quản lý các extension bổ sung
- **Hỗ trợ đa số extension**: VNCode hỗ trợ các extension code runner phổ biến trên marketplace
- **Quản lý extension**: Giao diện đơn giản để cài đặt, cập nhật, xóa extension
- **Lợi ích**: Mở rộng khả năng IDE mà không cần chỉnh sửa mã nguồn

### 3. Hỗ Trợ LSP (Language Server Protocol)
- **Thêm mới**: Tích hợp Python LSP Server cho khả năng code completion nâng cao
- **Chức năng LSP Python**:
  - Gợi ý từ khóa và hàm tự động
  - Phát hiện ký hiệu từ bộ đệm hiện tại
  - Hỗ trợ snippet từ các extension
  - Tự động hoàn thành dựa trên ngữ cảnh
- **Bổ sung trong tương lai**: LSP cho các ngôn ngữ khác

### 4. Hệ Thống Ưu Tiên Code Runner Extension
- **Tính năng**: Chuỗi fallback thông minh để thực thi mã với các extension
- **Thứ Tự Ưu Tiên**:
  1. Extension code-runner hỗ trợ ngôn ngữ này
  2. Bất kỳ extension code-runner nào có sẵn
  3. Cú pháp chạy tích hợp từ `TYPE_RUN_SYNTAX`
  4. Tin nhắn lỗi nếu không tìm thấy runner nào
- **Hiển thị**: Terminal sẽ hiển thị runner nào đang được sử dụng
- **Lợi ích**: Hệ thống runner có thể mở rộng; người dùng có thể ghi đè runner tích hợp bằng extension tùy chỉnh

---

## Cải Thiện

### Giao Diện Người Dùng (UI/UX)
- Thanh tab sạch sẽ hơn với tên tệp + nút đóng
- Hệ thống phân cấp trực quan hơn cho các dự án đa ngôn ngữ

### Chất Lượng Mã
- Loại bỏ tất cả emoji khỏi nhận xét mã (bây giờ chỉ văn bản)
- Cải thiện độ rõ ràng mã với các mô tả dạng chữ

### Kiến Trúc
- Các phương thức mới trong `run.py`:
  - `find_runner_for_file(file_path)`: Chuỗi ưu tiên extension
  - Cải thiện khám phá runner với priority chain tự động

---

## Chi Tiết Kỹ Thuật

### Tệp Được Sửa Đổi
- **run.py**
  - Cập nhật `about_app()`: Phiên bản được thay đổi từ 1.0 thành 1.1
  - Cải thiện khám phá runner: `find_runner_for_file()` với chuỗi ưu tiên

- **lsp_python.py** (nếu có)
  - Xác nhận: Không có emoji trong nhận xét (tuân thủ tiêu chuẩn mã hóa v1.1)

### Thư Viện Sử Dụng
- **PyQt5** - Giao diện người dùng
- **sys** - Hệ thống
- **json** - Xử lý JSON
- **os** - Hệ điều hành
- **collections** - Cấu trúc dữ liệu
- **pathlib** - Quản lý đường dẫn
- **importlib.util** - Nhập module
- **shutil** - Tiện ích shell

---

## Sửa Chữa Lỗi

- Loại bỏ sử dụng emoji trong nhận xét mã (bây giờ chỉ văn bản)
- Cải thiện quản lý mã với kỹ thuật tốt hơn

---

## Những Hạn Chế Đã Biết

- Hỗ trợ ngôn ngữ hiện tại: Python, C, C++, C#, Java, R, Rust, Go, Lua, Batch, Bash, Swift, Kotlin, PowerShell, Assembly

---

## Yêu Cầu Hệ Thống

- **Windows**: 8, 8.1, 10, 11 (bắt buộc 64-bit)
- **Python**: 3.8+ (khuyến nghị 3.10+)
- **PyQt5**: 5.15+
- **Các thư viện khác**: Giống như v1.0 (không có thư viện mới)

---

## Cài Đặt & Xây Dựng

### Chạy Từ Mã Nguồn
```bash
python run.py
```

**Yêu cầu**: Python v3.8+ phải được cài đặt

### Xây Dựng Tệp Thực Thi
```bash
pyinstaller --onedir --noconfirm --icon="icon_VNCode.ico" \
  --add-data "fill_module.py;." \
  --add-data "list_module.py;." \
  --add-data "icon_VNCode.ico;." \
  --add-data "close_hover.svg;." \
  --add-data "close.svg;." \
  run.py
```

---

## Tương Thích Ngược

✅ **Hoàn toàn tương thích ngược** với v1.0
- Các tệp cấu hình hiện có được di chuyển tự động
- Không có thay đổi phá vỡ API
- Tất cả các tính năng v1.0 được giữ lại

---

## Ghi Chú Di Chuyển Cho Người Dùng

1. **Extension**: Các extension code runner tiếp tục hoạt động với hệ thống ưu tiên mới


---

## Tín Dụng

**Nhóm Phát Triển**: Nguyễn Trường Lâm (VNCore Lab)  
**Đóng Góp Viên**: Cộng Đồng VNCode  
**Cảm Ơn Đặc Biệt**: Những người bảo trì list_module và fill_module

---

## Hỗ Trợ & Phản Hồi

Để báo cáo vấn đề, đề xuất hoặc gửi phản hồi:
- **Email**: nguyenvannghia1952tg@gmail.com
- **Nhóm**: VNCore Lab

---

## Ghi Chú Bản Quyền

VNCode sử dụng **100% Giấy Phép GPLv3**  
Phiên bản v1.1 - Năm 2025 - VNCore Lab (Nguyễn Trường Lâm)
- **GitHub**: [Link to repository]

---

## Changelog Summary

| Feature | Status | Lines Changed |
|---------|--------|-----------------|
| Code Runner Priority | ✅ Complete | ~100 lines |
| Emoji Removal | ✅ Complete | ~30 lines |
| **Total Improvements** | **✅** | **~130 lines** |

---

**Version**: VNCode IDE v1.1  
**Release Date**: April 15, 2026  
**Status**: Stable & Ready for Production

Thank you for using VNCode IDE!
