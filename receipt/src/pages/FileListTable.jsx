import React, { useState } from 'react';
import '../styles/FileListTable.css';
import FirstUpload from '../components/Banners';
import { documentService } from '../utils/api';

/**
 * FileListTable
 * Displays uploaded files fetched from the Django backend in a simple table
 */
const FileListTable = ({ 
  documents = [],
  onDelete, /* send a delete back to the API */
  isStatementsPage 
}) => {
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(10);
  const [searchTerm, setSearchTerm] = useState('');
  const [fileError, setFileError] = useState(null);

  /* Search documents */
  const filteredDocuments = documents.filter(doc => 
    doc.file_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    doc.meta?.merchant_name?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const totalPages = Math.max(1, Math.ceil(filteredDocuments.length / itemsPerPage));
  const startIndex = (currentPage - 1) * itemsPerPage;
  const paginatedDocs = filteredDocuments.slice(startIndex, startIndex + itemsPerPage);

  const handleDeleteClick = (id) => {
    if (onDelete) {
      onDelete(id);
    }
  };

  const handlePageChange = (newPage) => {
    if (newPage >= 1 && newPage <= totalPages) {
      setCurrentPage(newPage);
    }
  };

  if (documents.length === 0) {
    return <FirstUpload uploadType={isStatementsPage ? "statement" : "receipt"}/>;
  }

  return (
    <div className="file-list-container">
      {/* Search Bar */}
      <div className="table-controls" style={{ marginBottom: '15px' }}>
        <input 
          type="text" 
          placeholder="Search files by name or merchant..." 
          value={searchTerm}
          onChange={(e) => {
            setSearchTerm(e.target.value);
            setCurrentPage(1);
          }}
          style={{ padding: '8px', width: '300px', borderRadius: '4px', border: '1px solid #ccc' }}
        />
      </div>

      {fileError && <p style={{ color: 'red' }}>{fileError}</p>}

      {/* Table */}
      <table className="file-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ background: '#f9fafb', textAlign: 'left' }}>
            <th style={{ padding: '12px' }}>File Name</th>
            <th style={{ padding: '12px' }}>Uploaded At</th>
            {!isStatementsPage && <th style={{ padding: '12px' }}>Transaction Date</th>}
            {!isStatementsPage && <th style={{ padding: '12px' }}>Merchant</th>}
            {!isStatementsPage && <th style={{ padding: '12px' }}>Amount</th>}
            <th style={{ padding: '12px' }}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {paginatedDocs.map((doc) => (
            <tr key={doc.id} style={{ borderBottom: '1px solid #eee' }}>
              <td style={{ padding: '12px' }}>{doc.file_name}</td>
              <td style={{ padding: '12px' }}>
                {doc.uploaded_at ? new Date(doc.uploaded_at).toLocaleString() : 'N/A'}
              </td>
              {!isStatementsPage && <td style={{ padding: '12px' }}>
                {doc.meta.transaction_date ? new Date(doc.meta.transaction_date).toLocaleString() : 'N/A'}
              </td>}
              {!isStatementsPage && <td style={{ padding: '12px' }}>{doc.meta?.merchant_name || '-'}</td>}
              {!isStatementsPage && <td style={{ padding: '12px' }}>{doc.meta?.amount ? `${doc.meta.amount}${doc.meta.currency ? ` ${doc.meta.currency}` : ''}` : '-'}</td>}
              <td style={{ padding: '12px' }}>
                <button 
                  onClick={() => {
                    setFileError(null);
                    documentService
                      .openDocumentFile(doc.id, doc.category)
                      .catch(() => setFileError('This file could not be opened. Please try again later.'));
                  }}
                  className="btn-view"
                  style={{ marginRight: '8px', padding: '4px 8px', cursor: 'pointer' }}
                >
                  View
                </button>
                <button 
                  onClick={() => handleDeleteClick(doc.id)}
                  className="btn-delete"
                  style={{ padding: '4px 8px', color: 'red', cursor: 'pointer' }}
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Pagination and table options */}
      {totalPages > 1 && (
        <div className="pagination" style={{ marginTop: '15px', display: 'flex', justifyContent: 'center', gap: '10px' }}>
          <button 
            onClick={() => handlePageChange(currentPage - 1)} 
            disabled={currentPage === 1}
          >
            Prev
          </button>
          <span>Page {currentPage} of {totalPages}</span>
          <button 
            onClick={() => handlePageChange(currentPage + 1)} 
            disabled={currentPage === totalPages}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
};

export default FileListTable;