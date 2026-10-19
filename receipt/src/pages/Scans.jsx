import React, { useState, useEffect } from "react";
import Navbar from "../components/Navbar";
import FileDropZone from "./FileDrop";
import FileListTable from "./FileListTable";
import "../styles/PageFormat.css";
import { usePageTitle } from "../components/PageTitle";
import { documentService } from "../utils/api"

/*
  UI for Receipt uploads
  */
const Scans = () => {
  usePageTitle("Scans");
    const [documents, setDocuments] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState(null);

    /* Load receipts on mount */
    useEffect(() => {
        const fetchReceipts = async () => {
            try {
                setIsLoading(true);                
                const data = await documentService.getDocuments('receipt');
                setDocuments(data);
            } catch (err) {
                console.error("Failed to load receipts", err);
                setError("Failed to load your receipts. Please try again later.");
            } finally {
                setIsLoading(false);
            }
        };

        fetchReceipts();
    }, []);

    const handleFileUploaded = async (fileOrFiles) => {
        const actualFile = Array.isArray(fileOrFiles) ? fileOrFiles[0] : fileOrFiles;
        if (!actualFile) return false;
    
        const formData = new FormData();
        formData.append('file', actualFile);
        formData.append('category', 'receipt'); 

        try {
            /* Upload to Django */
            const newDoc = await documentService.uploadDocument(formData);
            
            setDocuments((prevDocs) => [newDoc, ...prevDocs]);
            return true;
        } catch (err) {
            console.error("Upload failed", err);
            alert("Upload failed: " + err.message);
            return false;
        }
    };

    const handleDelete = async (id) => {
        if (!window.confirm("Are you sure you want to delete this receipt?")) return;

        try {
            await documentService.deleteDocument(id, 'receipt');
            /* Upadate table immediately */
            setDocuments((prevDocs) => prevDocs.filter((doc) => doc.id !== id));

        } catch (err) {
            console.error("Failed to delete", err);
            alert("Failed to delete the receipt: " + err.message);
        }
    };

    return (
        <>
            <div className="container">
                <Navbar />
                <div className="scans-container">
                    <div className="scans-content">
                        <div className="scans-dashboard">
                            <div className="file-drop-wrapper">
                                <FileDropZone
                                    onUpload={handleFileUploaded}
                                    storageKey="uploadedScans"
                                    itemType="receipt"
                                />
                            </div>
                            <div className="file-view-wrapper">
                                {isLoading ? (
                                    <p>Loading your receipts...</p>
                                ) : error ? (
                                    <p style={{ color: "red" }}>{error}</p>
                                ) : (
                                    <FileListTable
                                        documents={documents}
                                        onDelete={handleDelete}
                                        isStatementsPage={false}
                                    />
                                )}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </>
    );
}

export default Scans;