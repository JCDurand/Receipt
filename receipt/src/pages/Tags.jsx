  /**
   * @file Tags.jsx
   * @description This file contains the Tags component, which provides a user interface for managing tags, tag templates, and tag assignments. It allows users to create, edit, delete, and assign tags to transactions and line items.
   */

import React, { useState, useEffect } from "react";
import Navbar from "../components/Navbar";
import TagPicker from "../components/TagPicker";
import { documentService } from "../utils/api";
import { getErrorMessage } from "../utils/errors";
import "../styles/Tags.css";
import { usePageTitle } from "../components/PageTitle";
import { formatDay } from "../utils/format";

const Tags = () => {
  usePageTitle("Tags & Templates");
  // Navigation and Data States
  const [activeTab, setActiveTab] = useState("assign");
  const [tags, setTags] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [lines, setLines] = useState([]);
  const [isLoading, setIsLoading] = useState(true);

    // Tag Creation and Template States
    const [newTagName, setNewTagName] = useState("");
    const [selectedParentId, setSelectedParentId] = useState("");
    const [templateSearch, setTemplateSearch] = useState("");
    const [templateMerchant, setTemplateMerchant] = useState("");
    const [templateTags, setTemplateTags] = useState([]);
    const [editingTemplateId, setEditingTemplateId] = useState(null);

    // UI State
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [feedback, setFeedback] = useState(null);
    const [deleteConfirmation, setDeleteConfirmation] = useState(null);

    const showFeedback = (type, message) => setFeedback({ type, message });

    useEffect(() => {
      if (!feedback) return undefined;
      const timeout = window.setTimeout(() => setFeedback(null), 6000);
      return () => window.clearTimeout(timeout);
    }, [feedback]);

    // Tag Editing states
    const [editingTag, setEditingTag] = useState(null);
    const [editTagName, setEditTagName] = useState("");
    const [editTagParent, setEditTagParent] = useState("");

    /**
     * Fetches initial data for tags, templates, and line items when the component mounts.
     * It handles loading states and ensures that the component is still mounted before updating state to prevent memory leaks.
     */
    useEffect(() => {
      let isMounted = true;
      setIsLoading(true);

      Promise.all([
        documentService.getTags(),
        documentService.getTemplates(),
        documentService.getLineItems()
      ])
        .then(([tagsData, templatesData, linesData]) => {
          if (!isMounted) return;
          setTags(tagsData || []);
          setTemplates(templatesData || []);
          setLines(linesData || []);
        })
        .catch((error) => {
          if (isMounted) showFeedback("error", getErrorMessage(error, "Tagging settings couldn't be loaded. Please try again."));
        })
        .finally(() => {
          if (isMounted) setIsLoading(false);
        });

      return () => {
        isMounted = false;
      };
    }, []);

    // Filter top-level tags (those without a parent) for rendering the hierarchy
    const topLevelTags = tags.filter(tag => !tag.parent);

    // Recursive Helpers

    /**
     * Recursively renders tag options for a dropdown or tree structure.
     * @param {Array} tagsList - The array of all tags.
     * @param {string|null} parentId - The ID of the parent tag.
     * @param {number} level - The current level in the hierarchy.
     * @param {string|null} excludeId - The ID of the tag to exclude from rendering.
     * @returns {React.Fragment[]} An array of rendered tag options.
     */
    const renderTagOptions = (tagsList, parentId = null, level = 0, excludeId = null) => {
      return tagsList
        .filter(t => t.parent === parentId && t.id !== excludeId)
        .map(tag => {
          const indent = level === 0 ? "" : "\u00A0\u00A0\u00A0\u00A0\u00A0\u00A0\u00A0\u00A0".repeat(level) + "└─ ";
          return (
            <React.Fragment key={tag.id}>
              <option value={tag.id}>
                {indent}{tag.name}
              </option>
              {renderTagOptions(tagsList, tag.id, level + 1, excludeId)}
            </React.Fragment>
          );
        });
    };

    /**
     * Recursive component that renders the visual tree of tags using CSS pseudo-elements for branches.
     * 
     * @param {Object} props
     * @param {Array} props.tagsList - Full array of available tags.
     * @param {string} props.parentId - The ID of the parent tag.
     * @param {number} props.level - Current depth level for styling logic.
     */
    const TagHierarchyTree = ({ tagsList, parentId, level = 1 }) => {
      const children = tagsList.filter(t => t.parent === parentId);
      if (children.length === 0) return null;

      return (
        <ul className={`tag-tree ${level === 1 ? "level-1" : ""}`}>
          {children.map(child => (
            <li key={child.id} className={`tag-tree-item ${level === 1 ? "level-1" : ""}`}>
              <div className="tag-tree-node">
                <button
                  type="button"
                  className="tag-sub-chip"
                  style={{
                    cursor: child.is_predefined ? "default" : "pointer",
                    margin: 0,
                    fontSize: "0.95rem",
                    fontFamily: "inherit",
                    border: "1px solid #cbd5e1",
                    backgroundColor: "#f1f5f9",
                    boxShadow: "0 1px 2px rgba(0,0,0,0.05)",
                    color: "#1e293b",
                    position: "relative",
                    zIndex: 2,
                    display: "inline-flex"
                  }}
                  onClick={() => !child.is_predefined && openEditTag(child)}
                  disabled={child.is_predefined}
                  aria-label={!child.is_predefined ? `Edit tag ${child.name}` : child.name}
                  title={!child.is_predefined ? "Edit tag" : undefined}
                >
                  {child.name} {!child.is_predefined && " ✎"}
                </button>
                {!child.is_predefined && (
                  <button
                    type="button"
                    className="tag-tree-delete"
                    onClick={() => handleDeleteTag(child)}
                    aria-label={`Delete tag ${child.name}`}
                  >
                    Delete
                  </button>
                )}
              </div>

              <TagHierarchyTree tagsList={tagsList} parentId={child.id} level={level + 1} />
            </li>
          ))}
        </ul>
      );
    };

    // Event handlers
    
    /**
     * Updates tags on a specific transaction or receipt line item.
     * 
     * @param {Object} line - The transaction object.
     * @param {Array} tagIds - Array of newly assigned tag IDs.
     */
    const handleAssignTags = async (line, tagIds) => {
      const save = line.kind === "statement_line" ? documentService.setTransactionTags : documentService.setItemTags;
      const saved = await save(line.id, tagIds);
      setLines((prev) => prev.map((l) => (l.kind === line.kind && l.id === line.id ? { ...l, tags: saved.tags } : l)));
    };

    /**
     * Handles dynamic tag creation directly from the TagPicker dropdown.
     * 
     * @param {string} name - Name of new tag 
     * @returns {Object} The created tag object
     */
    const handleCreateTagForPicker = async (name) => {
      const newTag = await documentService.createTag(name.trim());
      setTags((prev) => [...prev, newTag]);
      return newTag;
    };

    // Tag creation
    const handleCreateTag = async (e) => {
      e.preventDefault();
      if (!newTagName.trim()) {
        showFeedback("error", "Enter a name for the tag.");
        return;
      }
      setIsSubmitting(true);
      try {
        const created = await documentService.createTag(
          newTagName.trim(), 
          selectedParentId || null
        );
        setTags(prev => [...prev, created]);
        setNewTagName("");
        setSelectedParentId("");
        showFeedback("success", `“${created.name}” was created.`);
      } catch (err) {
        showFeedback("error", getErrorMessage(err, "The tag couldn't be created. Please try again."));
      } finally {
        setIsSubmitting(false);
      }
    };

    const openEditTag = (tag) => {
      setEditingTag(tag);
      setEditTagName(tag.name);
      setEditTagParent(tag.parent || "");
    };

    // Tag updates
    const handleUpdateTag = async () => {
      if (!editTagName.trim()) return;
      setIsSubmitting(true);
      try {
        const payload = { name: editTagName.trim() };
        payload.parent = editTagParent || null;
        
        const updated = await documentService.updateTag(editingTag.id, payload);
        setTags(prev => prev.map(t => t.id === editingTag.id ? updated : t));
        setEditingTag(null);
        showFeedback("success", `“${updated.name}” was updated.`);
      } catch (err) {
        showFeedback("error", getErrorMessage(err, "The tag couldn't be updated. Please try again."));
      } finally {
        setIsSubmitting(false);
      }
    };

    // Tag deletion
    const handleDeleteTag = (tag = editingTag) => {
      if (!tag) return;
      setDeleteConfirmation({
        kind: "tag",
        id: tag.id,
        name: tag.name,
        hasChildren: tags.some((candidate) => candidate.parent === tag.id)
      });
    };
    
    // Template event handlers
    const handleCreateTemplate = async (e) => {
      e.preventDefault();
      if (!templateSearch.trim()) {
        showFeedback("error", "Enter text for the automation rule to match.");
        return;
      }
      
      if (!templateMerchant.trim() && templateTags.length === 0) {
        showFeedback("error", "Add a merchant name, at least one tag, or both before saving.");
        return;
      }
      
      setIsSubmitting(true);
      try {
        const payload = { search_string: templateSearch.trim() };
        payload.merchant_name = templateMerchant.trim() || "";
        payload.tags = templateTags;

        const wasEditing = Boolean(editingTemplateId);
        if (wasEditing) {
          const updated = await documentService.updateTemplate(editingTemplateId, payload);
          setTemplates((prev) => prev.map((t) => (t.id === editingTemplateId ? updated : t)));
          setEditingTemplateId(null);
        } else {
          const created = await documentService.createTemplate(payload);
          setTemplates((prev) => [created, ...prev]);
        }
        
        // Reset form on success
        setTemplateSearch("");
        setTemplateMerchant("");
        setTemplateTags([]);
        showFeedback("success", wasEditing ? "The automation rule was updated." : "The automation rule was created.");
      } catch (err) {
        showFeedback("error", getErrorMessage(err, "The automation rule couldn't be saved. Please try again."));
      } finally {
        setIsSubmitting(false);
      }
    };

    const handleDeleteTemplate = (id) => {
      const template = templates.find((item) => item.id === id);
      setDeleteConfirmation({ kind: "template", id, name: template?.search_string || "this automation rule" });
    };

    const confirmDelete = async () => {
      if (!deleteConfirmation || deleteConfirmation.hasChildren) return;
      setIsSubmitting(true);
      try {
        if (deleteConfirmation.kind === "tag") {
          await documentService.deleteTag(deleteConfirmation.id);
          setTags((prev) => prev.filter((tag) => tag.id !== deleteConfirmation.id));
          setEditingTag(null);
          showFeedback("success", `“${deleteConfirmation.name}” was deleted.`);
        } else {
          await documentService.deleteTemplate(deleteConfirmation.id);
          setTemplates((prev) => prev.filter((template) => template.id !== deleteConfirmation.id));
          showFeedback("success", "The automation rule was deleted.");
        }
      } catch (err) {
        const fallback = deleteConfirmation.kind === "tag"
          ? "The tag couldn't be deleted. Please try again."
          : "The automation rule couldn't be deleted. Please try again.";
        showFeedback("error", getErrorMessage(err, fallback));
      } finally {
        setIsSubmitting(false);
        setDeleteConfirmation(null);
      }
    };

    const handleEditTemplateClick = (template) => {
      setTemplateSearch(template.search_string);
      setTemplateMerchant(template.merchant_name || "");
      const raw = template.tags || (template.tag ? [template.tag] : []);
      setTemplateTags(raw.map(t => (typeof t === "object" && t !== null ? t.id : t)));
      setEditingTemplateId(template.id);
      window.scrollTo({ top: 0, behavior: "smooth" });
    };

    const handleCancelEdit = () => {
      setTemplateSearch("");
      setTemplateMerchant("");
      setTemplateTags([]);
      setEditingTemplateId(null);
    };

    const handleTemplateTagChange = (newTags) => {
      if (!newTags) {
        setTemplateTags([]);
        return;
      }
      const ids = newTags.map(t => typeof t === 'object' ? t.id : t);
      setTemplateTags(ids);
    };

    // Tag rendering logic
    const renderContent = () => {
      if (isLoading) return <p className="loading-text">Loading your settings...</p>;

    switch (activeTab) {
      case "tags":
        return (
          <div className="settings-panel">
            <h2>Tag Management</h2>
            <p className="settings-desc">Organize your spending categories using infinite hierarchies.</p>
            
            {/* Tag creation form*/}
            <form onSubmit={handleCreateTag} className="settings-form">
              <input 
                type="text" 
                placeholder="New tag name..." 
                value={newTagName} 
                onChange={(e) => setNewTagName(e.target.value)} 
                disabled={isSubmitting}
                style={{ flex: 1.5 }}
                required
              />
              <select 
                value={selectedParentId} 
                onChange={(e) => setSelectedParentId(e.target.value)}
                disabled={isSubmitting}
              >
                <option value="">None (Make this a Parent Tag)</option>
                {renderTagOptions(tags)}
              </select>
              <button type="submit" className="btn-primary" disabled={isSubmitting}>
                {isSubmitting ? "Adding..." : "+ Create Tag"}
              </button>
            </form>
            
            {/* Hierarchical tag visualizer */}
            <div className="tag-hierarchy-list tags-scroll-region scroll-area">
              {topLevelTags.length === 0 && <p className="empty-state">No tags found.</p>}
              {topLevelTags.map(parent => (
                <div key={parent.id} className="tag-parent-card">
                  <div className="tag-parent-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #f1f5f9", paddingBottom: "10px" }}>
                    <strong>
                      {parent.name} {parent.is_predefined && <span className="default-badge">Default</span>}
                    </strong>
                    {!parent.is_predefined && (
                      <div className="tag-parent-actions">
                        <button type="button" onClick={() => openEditTag(parent)} className="btn-primary" style={{ padding: "8px 14px", fontSize: "0.85rem" }}>
                          Edit
                        </button>
                        <button type="button" onClick={() => handleDeleteTag(parent)} className="tag-tree-delete" aria-label={`Delete tag ${parent.name}`}>
                          Delete
                        </button>
                      </div>
                    )}
                  </div>
                  <TagHierarchyTree tagsList={tags} parentId={parent.id} />
                </div>
              ))}
            </div>
          </div>
        );
      case "automation":
        return (
          <div className="settings-panel">
            <h2>Tag Templates</h2>
            <p className="settings-desc">Automatically rename merchants or apply tags when text matches.</p>
            
            {/* Template creation/edit form */}
            <form onSubmit={handleCreateTemplate} className="settings-form">
              <input 
                type="text" 
                placeholder="If statement contains..." 
                value={templateSearch} 
                onChange={(e) => setTemplateSearch(e.target.value)} 
                disabled={isSubmitting}
                required
              />
              <span className="arrow-icon">➔</span>
              
              <input 
                type="text" 
                placeholder="Rename to (optional)..." 
                value={templateMerchant} 
                onChange={(e) => setTemplateMerchant(e.target.value)} 
                disabled={isSubmitting}
              />
              
              <div style={{ flex: 1, minWidth: "250px" }}>
                <TagPicker
                  available={tags}
                  selected={templateTags.map(item => {
                    const id = typeof item === "object" && item !== null ?item.id : item;
                    return tags.find(t => String(t.id) === String(id));
                  }).filter(Boolean)}
                  onChange={handleTemplateTagChange}
                  onCreateTag={handleCreateTagForPicker}
                  placeholder="Select Tags..."
                  disabled={isSubmitting}
                />
              </div>

                <button type="submit" className="btn-primary" disabled={isSubmitting}>
                  {isSubmitting ? "Saving..." : editingTemplateId ? "Update Rule" : "+ Add Rule"}
                </button>
                
                {editingTemplateId && (
                  <button type="button" onClick={handleCancelEdit} className="btn-cancel" disabled={isSubmitting}>
                    Cancel
                  </button>
                )}
              </form>

            <div className="tags-scroll-region scroll-area">
            <table className="settings-table">
              <thead>
                <tr>
                  <th>If text contains</th>
                  <th>Rename to</th>
                  <th>Auto-Tag</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {templates.length === 0 && (
                  <tr><td colSpan="4" className="empty-state">No automation rules created yet.</td></tr>
                )}
                {templates.map(template => {
                  const rawTags = template.tags || (template.tag ? [template.tag] : []);
                  return (
                    <tr key={template.id}>
                      <td><code>{template.search_string}</code></td>
                      <td><strong>{template.merchant_name || <span style={{ color: "#999", fontWeight: "normal" }}>-</span>}</strong></td>
                      <td>
                        {rawTags.length > 0 ? (
                          <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
                            {rawTags.map(tagItem => {
                              const tagId = typeof tagItem === "object"  && tagItem !== null ? tagItem.id : tagItem;
                              const t = tags.find(avail => String(avail.id) === String(tagId));
                              const label = t ? t.name : (typeof tagItem === "object" ? tagItem.name : null);
                              return label ?(
                                <span key = {String(tagId)} className = "tag-sub-chip" style={{margin:0}}>{label}</span>
                              ) :null;
                            })}
                          </div>
                        ) : (
                          <span style={{ color: "#999" }}>-</span>
                        )}
                      </td>
                      <td>
                        <div className="tag-parent-actions">
                          <button type="button" onClick={() => handleEditTemplateClick(template)} className="btn-primary template-edit-button">
                            Edit
                          </button>
                          <button type="button" onClick={() => handleDeleteTemplate(template.id)} className="tag-tree-delete">
                            Remove
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            </div>
          </div>
        );
      case "assign":
        return (
          <div className="settings-panel">
            <h2>Tag Assignment</h2>
            <p className="settings-desc">Quickly view and edit tags for all your transactions and line items.</p>
            
            <div className="transactions-scroll tags-scroll-region scroll-area" style={{ marginTop: "20px" }}>
              <table className="settings-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Name / Merchant</th>
                    <th>Tags</th>
                    <th>Total</th>
                  </tr>
                </thead>
                <tbody>
                  {lines.length === 0 ? (
                    <tr><td colSpan="4" className="empty-state">No line items found.</td></tr>
                  ) : (
                    lines.map(line => (
                      <tr key={`${line.kind}-${line.id}`} className={line.direction === "out" ? "line-tint-debit" : "line-tint-credit"}>
                        <td style={{ whiteSpace: "nowrap" }}>{formatDay(line.date)}</td>
                        <td>
                          <div><strong>{line.display_name || line.description}</strong></div>
                          {line.merchant && <div style={{ fontSize: "0.85em", color: "#666" }}>{line.merchant}</div>}
                        </td>
                        <td className="tag-cell" style={{ minWidth: "250px", position: "relative" }}>
                          <TagPicker
                            available={tags}
                            selected={line.tags}
                            onChange={(tagIds) => handleAssignTags(line, tagIds)}
                            onCreateTag={handleCreateTagForPicker}
                          />
                        </td>
                        <td className={`is-numeric nowrap line-amount ${line.direction === "out" ? "is-debit" : "is-credit"}`} style={{ fontWeight: 600 }}>
                          {Math.abs(Number(line.amount)).toFixed(2)}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        );
      default:
        return null;
    }
  };

    const feedbackBanner = feedback && (
      <div className={`tags-feedback tags-feedback-${feedback.type}`} role={feedback.type === "error" ? "alert" : "status"} aria-live={feedback.type === "error" ? "assertive" : "polite"}>
        <span className="tags-feedback-icon" aria-hidden="true">{feedback.type === "error" ? "!" : "✓"}</span>
        <span className="tags-feedback-message">{feedback.message}</span>
        <button type="button" onClick={() => setFeedback(null)} aria-label="Dismiss notification">&times;</button>
      </div>
    );

  return (
    <>
      <Navbar />
      <div className="container">
        <div className="tags-container">
          <div className="tags-content-wrapper">
            <div className="tags-header">
                <p>Manage your custom categories and automation rules.</p>
            </div>

                <div className="tags-layout">
                  <div className="tags-sidebar">
                    <h3>Settings</h3>
                    <ul>
                      <li 
                        className={activeTab === "assign" ? "active" : ""} 
                        onClick={() => setActiveTab("assign")}
                      >
                        Tag Assignment
                      </li>
                      <li 
                        className={activeTab === "tags" ? "active" : ""} 
                        onClick={() => setActiveTab("tags")}
                      >
                        Tag Management
                      </li>
                      <li 
                        className={activeTab === "automation" ? "active" : ""} 
                        onClick={() => setActiveTab("automation")}
                      >
                        Tag Templates
                      </li>
                    </ul>
                  </div>

                  <div className="tags-content">
                    {renderContent()}
                  </div>
                </div>
              </div>
            </div>
          </div>

        {/* Editing tag overlay modal */}
        {editingTag && (
          <div className="tag-edit-backdrop">
            <div className="settings-panel tag-edit-dialog" role="dialog" aria-modal="true" aria-labelledby="tag-edit-title">
              <h3 id="tag-edit-title" style={{ marginTop: 0 }}>Edit Tag</h3>
              <div className="settings-form" style={{ flexDirection: "column", gap: "15px", alignItems: "stretch", marginBottom: "0" }}>
                <label style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
                  <strong>Rename Tag:</strong>
                  <input type="text" value={editTagName} onChange={(e) => setEditTagName(e.target.value)} disabled={isSubmitting} />
                </label>
                <label style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
                  <strong>Move Tag (Nest inside):</strong>
                  <select value={editTagParent} onChange={(e) => setEditTagParent(e.target.value)} disabled={isSubmitting}>
                    <option value="">None (Make this a Parent Tag)</option>
                    {renderTagOptions(tags, null, 0, editingTag.id)}
                  </select>
                </label>
                <div style={{ display: "flex", justifyContent: "space-between", marginTop: "15px" }}>
                  <div style={{ display: "flex", gap: "10px" }}>
                    <button onClick={() => setEditingTag(null)} className="btn-cancel" disabled={isSubmitting}>
                      Cancel
                    </button>
                    <button onClick={handleUpdateTag} className="btn-primary" disabled={isSubmitting}>
                      {isSubmitting ? "Saving..." : "Save Changes"}
                    </button>
                  </div>
                  <button onClick={handleDeleteTag} className="btn-danger" disabled={isSubmitting}>
                    Delete Tag
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {deleteConfirmation && (
          <div
            className="tag-dialog-backdrop"
            onClick={(event) => {
              if (event.target === event.currentTarget && !isSubmitting) setDeleteConfirmation(null);
            }}
          >
            <section className="tag-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="tag-confirm-title">
              <p className="tag-confirm-eyebrow">Confirm deletion</p>
              <h2 id="tag-confirm-title">Delete {deleteConfirmation.kind === "tag" ? "tag" : "automation rule"}?</h2>
              <p className="tag-confirm-copy">
                {deleteConfirmation.hasChildren
                  ? <>“<strong>{deleteConfirmation.name}</strong>” still has subtags. Delete those first, then you can delete this tag.</>
                  : <>Permanently delete <strong>“{deleteConfirmation.name}”</strong>? This action cannot be undone.</>}
              </p>
              <div className="tag-confirm-actions">
                {deleteConfirmation.hasChildren ? (
                  <button type="button" className="btn-cancel" onClick={() => setDeleteConfirmation(null)}>
                    Got it
                  </button>
                ) : (
                  <>
                    <button type="button" className="btn-cancel" disabled={isSubmitting} onClick={() => setDeleteConfirmation(null)}>
                      Cancel
                    </button>
                    <button type="button" className="btn-danger" disabled={isSubmitting} onClick={confirmDelete}>
                      {isSubmitting ? "Deleting..." : "Delete permanently"}
                    </button>
                  </>
                )}
              </div>
            </section>
          </div>
        )}

        {feedbackBanner}
      </>
    );
  };

  export default Tags;