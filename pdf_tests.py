from fitz import Document, Page

doc: Document = Document()
page: Page = doc.new_page(width=1189, height=841)
print(f"{page.rect=}")

x, y = 33, 44
xref = page.insert_image((x, y, x + 200, y + 100), filename='images/RLMU_Stamp.png', keep_proportion=True,
                         overlay=True, rotate=page.rotation)

doc.save("example_pdfs/empty_stamp_with_prop.pdf")
doc.close()
