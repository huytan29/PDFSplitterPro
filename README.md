# PDF Splitter Pro

PDF Splitter Pro là ứng dụng Windows dùng để xem, sắp xếp, chỉnh sửa, tách và ghép
các trang PDF. Ứng dụng được tối ưu cho hồ sơ scan tiếng Việt, đặc biệt là Giấy
chứng nhận quyền sử dụng đất (GCN), Căn cước công dân (CCCD) và Chứng minh nhân dân
(CMND).

Ngoài việc đặt tên thủ công, chương trình có chế độ OCR tự đề xuất tên file. Mọi tên
được nhận dạng đều xuất hiện trong hộp thoại xem trước để người dùng kiểm tra và sửa
trước khi lưu; chương trình không tự ghi đè PDF nguồn.

## Chức năng chính

| Chức năng | Mô tả |
| --- | --- |
| Xem danh sách trang | Hiển thị ảnh thu nhỏ, vị trí hiện tại, trạng thái đã chọn và đã sửa. |
| Đổi thứ tự trang | Kéo thả trang sang trái/phải hoặc dùng hai nút **Sang trái/Sang phải**. |
| Chọn nhiều trang | Bấm thẻ trang để bật/tắt dấu ✓; hỗ trợ **Tích tất cả** và **Bỏ chọn**. |
| Chỉnh sửa trang | Xoay, lật, cắt, làm rõ, chuyển đen trắng, chèn chữ, hoàn tác và khôi phục ảnh gốc. |
| Tự sửa hướng | Dùng bố cục ảnh và OCR để sửa trang bị xoay 90°/180° hoặc bị lật gương. |
| Tách PDF | Tách một PDF thành nhiều file theo các khoảng trang, có bước xem trước và đặt tên. |
| Tự đặt tên | Nhận dạng GCN, CCCD và CMND; có nút bật/tắt độc lập. |
| Ghép trang | Chọn các vị trí trang bất kỳ rồi xuất thành một PDF mới. |
| Ảnh thành PDF | Nhập nhiều ảnh, chỉnh sửa, sắp xếp và xuất thành PDF 72–300 DPI. |
| Giao diện/OCR | Hỗ trợ tiếng Việt, English và chế độ OCR tự động. |

## Chạy nhanh bản phát hành

1. Mở thư mục `release`.
2. Chạy `PDFSplitterPro.exe`.
3. Bấm **Chọn** trong phần **PDF nguồn** để mở tài liệu.
4. Chọn **Thư mục lưu**.
5. Sắp xếp/chỉnh sửa trang nếu cần, nhập các khoảng trang rồi bấm
   **TÁCH PDF VÀ LƯU**.

Bản EXE là dạng một file, không yêu cầu cài Python. Tesseract OCR và dữ liệu ngôn ngữ
được đóng kèm trong bản phát hành.

> Nếu vừa cập nhật bản mới, cần đóng hoàn toàn cửa sổ đang chạy rồi mở lại
> `release\PDFSplitterPro.exe` để chương trình nạp mã mới.

## Quy trình sử dụng chi tiết

### 1. Mở PDF nguồn

Bấm **Chọn** ở dòng **PDF nguồn** và chọn một file `.pdf`. Sau khi mở thành công,
chương trình tạo dải ảnh thu nhỏ của toàn bộ các trang.

Khi mở tài liệu khác, các trạng thái của tài liệu trước như thứ tự trang, dấu ✓ và
chỉnh sửa trong bộ nhớ sẽ được làm mới.

### 2. Chọn trang và thay đổi thứ tự

Mỗi thẻ trong dải trang có hai trạng thái độc lập:

- Viền xanh biểu thị trang đang được xem/thao tác.
- Dấu ✓ màu xanh biểu thị trang đã được tích để chỉnh sửa hàng loạt hoặc **TỰ SỬA**.

Để đổi thứ tự:

1. Giữ chuột trái trên một thẻ trang.
2. Kéo sang vị trí mới; dải trang tự cuộn khi kéo gần mép trái/phải.
3. Thả chuột tại vị trí mong muốn.

Cũng có thể chọn một trang rồi bấm **◀ Sang trái** hoặc **Sang phải ▶**. Khi thứ tự
khác PDF gốc, thanh trạng thái hiển thị **Đã đổi thứ tự**.

#### Quy tắc quan trọng về số trang

Sau khi đổi thứ tự, số “Trang 1”, “Trang 2”… là **vị trí mới đang hiển thị**, không
phải số trang ban đầu trong PDF nguồn. Các chức năng sau đều dùng vị trí mới:

- khoảng trang dùng để tách PDF;
- danh sách trang dùng để ghép PDF;
- hộp thoại xem trước trước khi lưu;
- thứ tự trang trong file kết quả.

Ví dụ: kéo trang gốc số 8 lên đầu thì vị trí `1` trong khoảng tách/ghép chính là
trang gốc số 8.

### 3. Chỉnh sửa thủ công

Chọn một trang hoặc tích nhiều trang, sau đó bấm **CHỈNH SỬA**. Nếu không có dấu ✓,
chương trình chỉnh trang đang được chọn. Nếu có dấu ✓, chương trình mở toàn bộ các
trang đã tích.

Các thao tác có sẵn:

- xoay trái/phải 90°;
- lật ngang hoặc lật dọc;
- kéo chọn vùng cắt và áp dụng cắt;
- làm rõ tài liệu bằng cân bằng sáng, tăng tương phản và làm nét;
- chuyển ảnh sang đen trắng;
- thêm chữ với nội dung, kích thước và màu tùy chọn;
- xóa phần chữ vừa thêm gần nhất;
- hoàn tác;
- khôi phục ảnh gốc.

Trong chế độ nhiều trang, giữ `Ctrl` hoặc `Shift` để chọn nhiều mục. Xoay, lật, làm
rõ và đen trắng được áp dụng hàng loạt cho các mục đang chọn. Cắt và chèn chữ chỉ áp
dụng cho trang đang xem nhằm tránh sửa nhầm nhiều trang.

Bấm **ÁP DỤNG THAY ĐỔI** để đưa kết quả về cửa sổ chính. Các thay đổi lúc này chỉ
nằm trong bộ nhớ và thẻ trang sẽ có nhãn **(đã sửa)**. PDF nguồn vẫn giữ nguyên.

### 4. Tự động sửa hướng trang

1. Bấm các thẻ cần xử lý để trên ảnh xuất hiện dấu ✓.
2. Chọn ngôn ngữ OCR:
   - **Tự động**: dùng cả tiếng Việt và English;
   - **Tiếng Việt**: chỉ dùng dữ liệu `vie`;
   - **English**: chỉ dùng dữ liệu `eng` và chuyển nhãn giao diện sang tiếng Anh.
3. Bấm **✦ TỰ SỬA**.
4. Kiểm tra ảnh thu nhỏ và trạng thái **(đã sửa)** trước khi tách/ghép.

Thuật toán được thiết kế thận trọng: chỉ xoay hoặc lật khi tín hiệu bố cục/OCR đủ
rõ. Trang mờ, quá ít chữ hoặc kết quả không chắc chắn sẽ được giữ nguyên thay vì bị
xoay ngẫu nhiên. Với một số bìa GCN scan ngang, chương trình còn dùng vị trí quốc huy
và cấu trúc dòng chữ để xác định chiều ngay cả khi OCR yếu.

### 5. Tách PDF

Nhập mỗi khoảng trang trên một dòng trong ô **Khoảng trang**:

```text
1-2
3-4
5-8
```

Quy tắc nhập:

- vị trí trang bắt đầu từ `1`;
- mỗi dòng phải có đúng định dạng `bắt_đầu-kết_thúc`;
- đầu khoảng không được lớn hơn cuối khoảng;
- khoảng phải nằm trong tổng số trang của PDF;
- khoảng được tính theo thứ tự đang hiển thị sau khi kéo thả.

Khi bấm **TÁCH PDF VÀ LƯU**, mỗi khoảng mở một hộp thoại riêng. Hộp thoại cho phép:

- xem toàn bộ các trang của khoảng;
- xem cả những chỉnh sửa đang nằm trong bộ nhớ;
- xoay đồng thời toàn bộ khoảng 90° hoặc 180°;
- phóng to/thu nhỏ phần xem trước;
- nhập hoặc sửa tên file;
- bấm **Tiếp** để xác nhận khoảng hiện tại hoặc **Hủy** để dừng toàn bộ lần tách.

Nếu file đích đã tồn tại, chương trình không ghi đè mà tự thêm hậu tố `(1)`, `(2)`…
vào tên file mới.

### 6. Tự động đặt tên khi tách

Nút **TỰ ĐẶT TÊN: BẬT/TẮT** chỉ kiểm soát việc OCR đề xuất tên. Nó không thay đổi
các chức năng sắp xếp, chỉnh sửa hoặc tách PDF.

- **TẮT**: ô tên file để trống như luồng đặt tên thủ công.
- **BẬT**: chương trình đọc tối đa hai trang đầu của từng khoảng, đề xuất tên và
  hiển thị lý do nhận dạng trong hộp thoại xem trước.

Tên đề xuất luôn có thể sửa. Nếu không đủ chắc chắn, chương trình để người dùng nhập
thủ công thay vì cố tạo một tên có khả năng sai.

#### GCN – Giấy chứng nhận

Định dạng tên:

```text
<hai chữ cái sê-ri> <số phát hành>
```

Ví dụ:

```text
BQ 832413
BU 748584
```

Chương trình:

- xác nhận trang có tiêu đề **GIẤY CHỨNG NHẬN** hoặc **QUYỀN SỬ DỤNG**;
- thử cả bốn hướng 0°/90°/180°/270°;
- OCR nhiều vùng gần góc dưới của bìa bằng các kênh màu khác nhau;
- chọn mã có đồng thuận tốt giữa các lần đọc;
- chấp nhận sê-ri phát hành phổ biến gồm 6 chữ số và một số mẫu cũ 8 chữ số;
- đối chiếu tên file/thư mục nguồn chỉ như một gợi ý, không coi đó là dữ liệu đúng
  tuyệt đối;
- có thể dùng gợi ý nguồn để hoàn thiện một chữ số cuối bị cắt mép, nhưng chỉ khi
  bằng chứng OCR và bìa GCN phù hợp;
- để trống và yêu cầu kiểm tra thủ công khi các mã xung đột hoặc ảnh quá mờ.

Việc không tin tuyệt đối tên thư mục là có chủ đích: dữ liệu thực tế có thể chứa mã
cũ hoặc mã đã nhập sai, trong khi số in trực tiếp trên bìa mới là nguồn chính.

#### CCCD – Căn cước công dân

Định dạng tên:

```text
<Họ và tên> <12 chữ số CCCD>
```

Ví dụ:

```text
Trần Quang Hiến 034062002746
```

Thứ tự nhận dạng:

1. Đọc mã QR ở góc thẻ nếu ảnh chứa QR hợp lệ.
2. Nếu QR không đọc được, xác nhận tiêu đề CCCD/Căn cước.
3. OCR riêng vùng số định danh 12 chữ số.
4. OCR tên bằng nhiều vùng và nhiều kiểu bố cục.
5. Chỉ chấp nhận dòng tên có cấu trúc phù hợp với tên người Việt; loại các nhãn như
   “Ngày sinh”, “Full name”, “Nationality”…

Tên trong thư mục nguồn chỉ được dùng để khôi phục dấu tiếng Việt khi phần chữ không
dấu trùng với kết quả OCR. Chương trình không lấy tên thư mục thay cho tên trên thẻ.

#### CMND – Chứng minh nhân dân mẫu cũ

Định dạng tên giống CCCD:

```text
<Họ và tên> <số CMND>
```

CMND hỗ trợ số 9 chữ số và mẫu 12 chữ số. Chương trình phải nhận thấy tiêu đề
**CHỨNG MINH NHÂN DÂN**, số và họ tên hợp lệ trước khi đề xuất.

#### Ký tự trong tên file

Trước khi lưu, tên được chuẩn hóa Unicode và loại các ký tự Windows không cho phép:

```text
< > : " / \ | ? *
```

Khoảng trắng thừa được rút gọn và tên tối đa 160 ký tự.

### 7. Ghép các trang thành một PDF

Nhập lựa chọn vào ô **GHÉP TRANG THÀNH 1 PDF**, sau đó bấm
**CHỌN VÀ GHÉP PDF**.

Các định dạng hợp lệ:

```text
1,3
1-3
1,3,5
1-3,5,8-10
```

Có thể dùng dấu phẩy, dấu chấm phẩy hoặc xuống dòng để phân tách. Các trang không
được lặp lại và khoảng phải tăng dần. File ghép tuân theo thứ tự trang đang hiển thị
và bao gồm các chỉnh sửa đang nằm trong bộ nhớ. Chương trình không cho phép chọn
chính PDF nguồn làm file đích.

### 8. Chuyển ảnh thành PDF

Bấm **ẢNH → PDF** ở góc trên bên phải. Định dạng ảnh hỗ trợ:

```text
PNG, JPG/JPEG, BMP, TIFF và WebP
```

Quy trình:

1. Bấm **Thêm ảnh** và chọn một hoặc nhiều ảnh.
2. Dùng **Lên/Xuống** để sắp xếp thứ tự trang.
3. Chỉnh sửa từng ảnh nếu cần.
4. Chọn độ phân giải từ 72 đến 300 DPI; mặc định là 150 DPI.
5. Bấm **XUẤT PDF** và chọn nơi lưu.

Ảnh được tự điều chỉnh theo thông tin xoay EXIF trước khi đưa vào trình chỉnh sửa.

## An toàn dữ liệu và chất lượng đầu ra

- PDF nguồn không bị ghi đè khi tách, ghép hoặc chỉnh sửa.
- Mọi thay đổi trang chỉ nằm trong bộ nhớ cho tới khi xuất file.
- Đóng hộp thoại chỉnh sửa bằng **Hủy** sẽ bỏ bản đang làm việc trong hộp thoại đó.
- Trang không chỉnh sửa được sao chép trực tiếp từ PDF nguồn.
- Chỉ trang đã chỉnh sửa mới được dựng lại thành ảnh để hỗ trợ cắt, lật, lọc scan và
  chèn chữ; vì vậy chữ/vector trên trang đó sẽ không còn là đối tượng PDF riêng.
- Tên tách bị trùng được tự thêm hậu tố, tránh ghi đè file cũ.
- OCR chỉ là gợi ý. Luôn kiểm tra ảnh, số phát hành/số định danh và tên người trước
  khi bấm **Tiếp**.

## Cài đặt môi trường phát triển

### Yêu cầu

- Windows 10/11 64-bit;
- Python 3.11 trở lên;
- Tesseract OCR có dữ liệu `vie`, `eng` và `osd`;
- các thư viện trong `requirements.txt`.

### Tạo môi trường và cài thư viện

Mở PowerShell tại thư mục dự án:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Chạy từ mã nguồn:

```powershell
.\.venv\Scripts\python.exe main.py
```

Các thư viện chính:

- `PySide6`: giao diện desktop;
- `PyMuPDF`: mở, render và tạo trang PDF;
- `pypdf`: sao chép, tách và ghép trang PDF chưa chỉnh sửa;
- `Pillow`: xử lý ảnh;
- `pytesseract`: gọi bộ máy OCR;
- `zxing-cpp`: đọc QR trên CCCD.

## Cấu hình Tesseract OCR

Ứng dụng tìm `tesseract.exe` theo thứ tự:

1. biến môi trường `TESSERACT_CMD`;
2. `resources\tesseract\tesseract.exe` trong dự án hoặc gói PyInstaller;
3. `C:\Program Files\Tesseract-OCR\tesseract.exe`;
4. `%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe`.

Thư mục `resources\tesseract\tessdata` phải có tối thiểu:

```text
vie.traineddata
eng.traineddata
osd.traineddata
```

Có thể chỉ định bản Tesseract khác cho phiên PowerShell hiện tại:

```powershell
$env:TESSERACT_CMD = 'C:\Program Files\Tesseract-OCR\tesseract.exe'
.\.venv\Scripts\python.exe main.py
```

## Đóng gói bản EXE

Cài PyInstaller trong môi trường phát triển:

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
```

Đóng gói theo file cấu hình của dự án:

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean `
  --distpath release `
  --workpath build `
  PDFSplitterPro.spec
```

Kết quả là:

```text
release\PDFSplitterPro.exe
```

`PDFSplitterPro.spec` tạo bản `one-file`, ẩn cửa sổ console, gắn biểu tượng Windows,
đóng kèm logo và toàn bộ thư mục `resources\tesseract` khi tìm thấy
`resources\tesseract\tesseract.exe`.

Sau khi build nên kiểm tra tối thiểu:

1. EXE mở được và giao diện phản hồi bình thường.
2. Chọn được PDF và hiển thị đủ ảnh thu nhỏ.
3. Kéo trang từ đầu xuống cuối và ngược lại.
4. Tách một khoảng sau khi đổi thứ tự.
5. Bật tự đặt tên và thử ít nhất một GCN, CCCD và CMND.
6. Kiểm tra GCN scan ngang, mờ, cắt sát mép và mã có chữ dễ nhầm như `BQ/BO`.
7. Kiểm tra tên đã nhận dạng trong hộp thoại trước khi lưu.

## Kiểm tra mã nguồn

Kiểm tra lỗi cú pháp toàn bộ ứng dụng:

```powershell
.\.venv\Scripts\python.exe -m compileall -q app main.py
```

Kiểm tra các dòng thừa/khoảng trắng có thể gây lỗi bản vá:

```powershell
git diff --check
```

Không nên đánh giá thuật toán OCR chỉ bằng ảnh lý tưởng. Bộ kiểm thử hồi quy cần chứa
cả các trường hợp:

- GCN bìa hồng/đỏ, scan ngang và scan dọc;
- số phát hành mờ hoặc sát mép;
- OCR nhầm chữ sê-ri (`BQ` thành `BO`) hoặc lặp/mất một chữ số;
- tên thư mục nguồn không trùng số in trên bìa;
- CCCD mẫu cũ, mẫu mới có QR và ảnh không có QR;
- CMND 9 số và 12 số;
- tài liệu không thuộc ba loại trên để đảm bảo chương trình không đặt tên bừa.

## Cấu trúc dự án

```text
PDFSplitterPro/
├── app/
│   ├── models/
│   │   └── editable_image.py    # mô hình ảnh và chú thích chữ
│   ├── services/
│   │   ├── auto_correct.py      # tự xoay/lật bằng OCR và bố cục
│   │   ├── auto_naming.py       # nhận dạng GCN, CCCD, CMND
│   │   ├── preview.py           # dựng ảnh xem trước PDF
│   │   └── splitter.py          # tách/ghép và áp dụng chỉnh sửa
│   └── ui/
│       ├── image_pdf_dialog.py  # chỉnh sửa ảnh/trang và ảnh → PDF
│       ├── main_window.py       # cửa sổ chính, kéo thả và luồng xuất
│       └── rename_dialog.py     # xem trước, xoay và xác nhận tên
├── resources/
│   ├── tesseract/               # bộ OCR và dữ liệu ngôn ngữ
│   └── pdf_lightning_logo*      # biểu tượng ứng dụng
├── release/                     # bản EXE phát hành
├── main.py                      # điểm khởi động
├── PDFSplitterPro.spec          # cấu hình PyInstaller
├── requirements.txt             # thư viện Python
└── README.md
```

## Xử lý sự cố

### Không tự đặt tên được

- Kiểm tra nút đang ở trạng thái **TỰ ĐẶT TÊN: BẬT**.
- Kiểm tra đủ `vie.traineddata` và `eng.traineddata`.
- Đảm bảo bìa GCN hoặc mặt trước CCCD/CMND nằm trong một trong hai trang đầu của
  khoảng tách.
- Kiểm tra ảnh không bị cắt mất toàn bộ mã/tên.
- Nếu thông báo màu vàng xuất hiện, nhập tên thủ công; đây là cơ chế an toàn khi OCR
  không đủ chắc chắn.

### GCN nhận sai số phát hành

- So sánh tên đề xuất với số in trực tiếp ở góc dưới bìa.
- Không dựa hoàn toàn vào tên thư mục vì đó chỉ là gợi ý đối chiếu.
- Nếu ảnh bị cắt sát số, chỉnh lại vùng scan hoặc nhập thủ công.
- Lưu lại mẫu gây lỗi trong bộ hồi quy trước khi thay đổi thuật toán để tránh sửa mẫu
  này nhưng làm sai mẫu khác.

### Kéo trang nhưng thứ tự không đổi

- Giữ chuột và kéo đủ xa để con trỏ chuyển sang trạng thái đang nắm.
- Thả trực tiếp trên thẻ đích; kéo gần mép để dải trang tự cuộn.
- Có thể dùng **Sang trái/Sang phải** để kiểm tra nhanh.
- Xác nhận thanh trạng thái xuất hiện **Đã đổi thứ tự**.

### TỰ SỬA không thay đổi trang

- Trang phải có dấu ✓ trước khi bấm **TỰ SỬA**.
- Kết quả “không phát hiện trang cần xoay/lật” không phải lỗi: thuật toán giữ nguyên
  khi tín hiệu không đủ rõ.
- Thử chọn đúng ngôn ngữ OCR hoặc dùng **Tự động**.

### Chỉnh sửa đã làm nhưng file kết quả không có

- Trong cửa sổ chỉnh sửa phải bấm **ÁP DỤNG THAY ĐỔI**.
- Sau đó phải xuất bằng **TÁCH PDF VÀ LƯU** hoặc **CHỌN VÀ GHÉP PDF**.
- Nhãn **(đã sửa)** trên thẻ trang xác nhận thay đổi đang nằm trong bộ nhớ.

### EXE mở chậm

Bản phát hành là dạng một file nên Windows cần giải nén thành phần vào thư mục tạm ở
lần mở. OCR lần đầu trên tài liệu scan độ phân giải cao cũng có thể mất thêm thời
gian. Không mở nhiều bản ứng dụng đồng thời khi đang OCR một hồ sơ lớn.

## Giới hạn hiện tại

- Tự đặt tên chỉ hỗ trợ GCN, CCCD và CMND Việt Nam.
- OCR phụ thuộc chất lượng scan, độ nghiêng, độ mờ, vùng bị cắt và kiểu tài liệu.
- GCN có bố cục hoàn toàn khác hoặc mã nằm ngoài các vùng thường gặp có thể cần nhập
  tay.
- Tên tiếng Việt bị mờ có thể mất dấu; người dùng cần xác nhận ở hộp thoại.
- Khi sửa hình ảnh của một trang, trang đó được dựng lại dưới dạng ảnh trong PDF kết
  quả; khả năng tìm kiếm/chọn chữ gốc của riêng trang đó có thể bị mất.

## Nguyên tắc khi thay đổi nhận dạng OCR

1. Không coi tên file hoặc tên thư mục là dữ liệu đúng tuyệt đối.
2. Ưu tiên nội dung in trực tiếp trên tài liệu và đồng thuận giữa nhiều lần OCR.
3. Không tự đặt tên khi số/tên có xung đột chưa giải quyết được.
4. Mọi đề xuất phải cho phép người dùng xem và sửa trước khi lưu.
5. Chạy lại toàn bộ bộ hồi quy GCN/CCCD/CMND trước khi đóng gói EXE.
6. Chạy thử chính EXE trong thư mục `release`, không chỉ chạy từ mã nguồn.
