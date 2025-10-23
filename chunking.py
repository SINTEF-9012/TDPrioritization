import os
import fitz

from haystack import Document
from haystack.components.preprocessors import DocumentSplitter


def convert_chunked_text_to_haystack_documents():
    chunked_dic = convert_pdf_files_to_chunked_text()
    documents = []
    
    for file_name, file_info_dic in chunked_dic.items():
        meta = file_info_dic["metadata"]
        text = file_info_dic["text"]
        
        meta.pop("encryption")

        meta["chunked"] = True
        meta["type"] = "article"
        meta["file_name"] = file_name

        doc = Document(meta=meta, content=text)
        documents.append(doc)

        chunked_documents = chunk_documents(documents)

    return chunked_documents

def convert_pdf_files_to_chunked_text():
    dic = {}

    for filename in os.listdir("articles"):
        if filename.endswith(".pdf"):
            text=""
            full_path = os.path.join("articles", filename)
            file_dic = {}

            doc = fitz.open(full_path)

            for page in doc:
                text += page.get_text("text")

            file_dic["metadata"] = doc.metadata
            file_dic["text"] = text

            dic[filename] = file_dic

    return dic

def chunk_documents(documents, chunk_size=10, overlap=2):

    splitter = DocumentSplitter(split_by="sentence", split_length=chunk_size, split_overlap=overlap, split_threshold=chunk_size)
    splitter.warm_up()
    chunks = splitter.run(documents=documents)

    for doc in chunks["documents"]:
        doc.meta = {k: v for k, v in doc.meta.items() if not k.startswith("_split_overlap")}


    return chunks["documents"]

if __name__ == "__main__":
    documents = convert_chunked_text_to_haystack_documents()

    print(len(documents))
