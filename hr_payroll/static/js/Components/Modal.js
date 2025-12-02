import React from 'react';

const Modal = ({ isOpen, children }) => {
    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
            <div className="bg-white rounded-lg p-4">
                {children}
            </div>
        </div>
    );
};

export default Modal;
