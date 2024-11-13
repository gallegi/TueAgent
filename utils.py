import fitz

def read_and_concat_pdf(retrieved_pdf_data, target_size=(595, 842)):
    """
    Concatenates specific pages from multiple PDFs into a single PDF with a uniform page size.
    
    Args:
        retrieved_pdf_data (dict): A dictionary where keys are PDF file paths, and values are lists of page numbers to extract.
        target_size (tuple): A tuple specifying the target page width and height in points. Defaults to A4 size (595x842 points).
        
    Returns:
        fitz.Document: A new PDF document with concatenated pages.
    """
    # Create a new PDF for output
    new_document = fitz.open()
    

    # increase continuity of pages_to_extract
        # new_pages_to_extract = set()
        # margin = 1
        # for i, page_num in enumerate(pages_to_extract): 
        #     for offset in range(-margin, margin+1):
        #         if page_num + offset < 0:
        #             continue
        #         new_pages_to_extract.add(page_num + offset)    
        # 

    target_size = ()

    for input_pdf_path, pages_to_extract in retrieved_pdf_data.items():
        # pages_to_extract = sorted(pages_to_extract)
        
        # Open the input PDF
        document = fitz.open(input_pdf_path)
        
        # Loop through the specified pages and extract them
        for page_num in pages_to_extract:
            if page_num < len(document):
                # Extract the page
                page = document.load_page(page_num)

                if not target_size:
                    target_size = (page.rect.width, page.rect.height)

                # # Resize to target size if needed
                # scale_x = target_size[0] / src_rect.width
                # scale_y = target_size[1] / src_rect.height
                # scale = min(scale_x, scale_y)  # Maintain aspect ratio
                
                # Create a new page in the target document with the specified target size
                new_page = new_document.new_page(width=target_size[0], height=target_size[1])
                
                # Place the page onto the new page centered, preserving scale
                # matrix = fitz.Matrix(scale, scale)
                # offset_x = (target_rect.width - src_rect.width * scale) / 2
                # offset_y = (target_rect.height - src_rect.height * scale) / 2
                # matrix = matrix.pretranslate(offset_x, offset_y)
                
                # Render the source page onto the new page
                new_page.show_pdf_page(new_page.rect, document, page_num)
            else:
                print(f"Page {page_num} does not exist in the document.")

        document.close()

    return new_document