import React from "react";
import upload_logo from "../assets/upload_logo.png";
import "../styles/Banners.css"

const FirstUpload = (props) => {
    return (
        <>
        <div className="first-upload-container">
            <div className="first-upload-image">
                <img src={upload_logo} alt="upload logo" />
            </div>
            <div className="first-upload-desc">
                You have not yet uploaded a {props.uploadType}. Add {props.uploadType}s in the upload box to see them displayed here.
            </div>
        </div>
        </>
    )
}

export default FirstUpload;