from django import forms


class ScoreBulkUploadForm(forms.Form):
    excel_file = forms.FileField(label="Excel file (.xlsx)")

    def clean_excel_file(self):
        excel_file = self.cleaned_data["excel_file"]
        if not excel_file.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("Please upload a .xlsx Excel file.")
        return excel_file
