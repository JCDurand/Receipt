"""
Utility functions for document uploads and file handling.
"""
import os
import uuid
from datetime import datetime
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage

MAX_UPLOAD_SIZE = getattr(settings, 'MAX_UPLOAD_SIZE', 50 * 1024 * 1024)
ALLOWED_DOCUMENT_EXTENSIONS = getattr(settings, 'ALLOWED_DOCUMENT_EXTENSIONS', 
                                      ['.pdf', '.csv'])
CATEGORY_DIR_MAP = {
    'receipt': 'receipts',
    'statement': 'statements',
}
def validate_document_file(file):
    """
    Validate that uploaded file is either PDF or CSV.
    
    Args:
        file: Django UploadedFile object
        
    Raises:
        ValidationError: If file extension is not allowed
    """
    if not file:
        raise ValidationError("No file provided.")
    
    file_name = file.name.lower()
    file_ext = os.path.splitext(file_name)[1]

    if file.size > MAX_UPLOAD_SIZE:
        raise ValidationError(f"File size exceeds maximum limit of {MAX_UPLOAD_SIZE} MB.")
    
    if file_ext not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise ValidationError(
            f"File type '{file_ext}' is not allowed. "
            f"Only {', '.join(ALLOWED_DOCUMENT_EXTENSIONS)} files are permitted."
        )
    
    # Check MIME type for additional safety
    if file_ext == '.pdf':
        if not file.content_type or 'pdf' not in file.content_type.lower():
            raise ValidationError(
                "File appears to be a PDF but has an incorrect MIME type."
            )
    elif file_ext == '.csv':
        if file.content_type and 'text' not in file.content_type.lower():
            raise ValidationError(
                "File appears to be a CSV but has an incorrect MIME type."
            )
    
    return file

# A function to generate a safe relative path to a file in the media folder
def generate_media_relative_path(category, filename):
    category_dir = CATEGORY_DIR_MAP.get(category, 'documents')

    base_name, ext = os.path.splitext(os.path.basename(filename))
    safe_base_name = "".join(c for c in base_name if c.isalnum() or c in ('-', '_'))

    unique_prefix = uuid.uuid4().hex[:8]
    unique_filename = f"{unique_prefix}_{safe_base_name}{ext.lower()}"

    now=datetime.now()
    year_month = now.strftime('%Y/%m')

    return f"{category_dir}/{year_month}/{unique_filename}"

def save_uploaded_file(file, category):
    validate_document_file(file)
    relative_path = generate_media_relative_path(category, file.name)

    saved_path = default_storage.save(relative_path, file)
    return saved_path

def delete_stored_file(file_path):
    if file_path and default_storage.exists(file_path):
        default_storage.delete(file_path)
        return True
    return False