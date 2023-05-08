import openpyxl as xl
from autoRLMU import AnnotationMaker

# **********************************************************
# there is a suspicion that real links from UNICA
# will not work as direct links to pdf, needs to be checked
# **********************************************************

wb = xl.load_workbook('loop_diagrams.xlsx')
sheet = wb['check_sheet']
loops = []

# for each row in 'check_sheet' sheet
for row in range(2, sheet.max_row + 1):
    # if an empty row - stop
    if sheet.cell(row, 1).value is None:
        break

    # clear result
    sheet.cell(row, 4).value = ''

    # save in dict
    loop = {"Doc Number": sheet.cell(row, 1).value, "Name": sheet.cell(row, 2).value,
            "Link": sheet.cell(row, 3).hyperlink.display}

    # for some reason sometimes .hyperlink.display has None, so we try to use the value instead
    if loop["Link"] is None:
        loop["Link"] = sheet.cell(row, 3).value

    loops.append(loop)

    # creating object
    pdf_path_annotated: str = f'pdfs/{loop["Doc Number"]}.pdf'
    loop_drawing = AnnotationMaker(pdf_path_annotated)

    # trying to make a redline
    if loop_drawing.make_redline(loop['Link'], is_link=True):
        loop["Result"] = 'Success'
    else:
        loop["Result"] = loop_drawing.get_error_description()

    # filling the result in the Excel file
    sheet.cell(row, 4).value = loop["Result"]

try:
    wb.save('loop_diagrams.xlsx')
except Exception as e:
    print(f'Cannot save the excel file: {str(e)}')

wb.close()
