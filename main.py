import openpyxl as xl
from autoRLMU import AnnotationMaker

# link = 'https://sww-llsak.sakhalinenergy.ru/glasseic/livelink.exe?func=ll&objId=10162950&objAction=browse' \
#        '&logStopConditionID=2931423_-2138710905_1_open'
link = 'https://github.com/said46/autoRLMU/raw/main/pdfs/6.pdf'

# autoRLMU.make_redline('pdfs/1.pdf')
# autoRLMU.make_redline(link, is_link=True)
loop = AnnotationMaker()
loop.make_redline(link, is_link=True)

# loop.make_redline('pdfs/1.pdf')
# ************** STOP HERE FOR NOW ********************
quit()

# *****************************************************
# Code Excel processing after trying to download from UNICA
# *****************************************************
wb = xl.load_workbook('loop_diagrams.xlsx')
sheet = wb['check_sheet']
list_of_loops = []
for row in range(2, sheet.max_row + 1):
    if sheet.cell(row, 1).value is None:
        break
    loop = {"DocNumber": sheet.cell(row, 1).value, "Name": sheet.cell(row, 2).value,
            "Link": sheet.cell(row, 3).hyperlink.display}
    print(loop)
    list_of_loops.append(loop)
wb.close()
