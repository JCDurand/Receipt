import { useState, useCallback } from 'react';
import axiosClient from '../api/axiosClient';

export const useTemplates = () => {
    const [templates, setTemplates] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const fetchTemplates = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await axiosClient.get('/templates/');
            setTemplates(response.data);
        } catch (err) {
            setError(err.response?.data?.error || 'Failed to fetch templates');
        } finally {
            setLoading(false);
        }
    }, []);

    const createTemplate = async (searchString, merchantName) => {
        setLoading(true);
        setError(null);
        try {
            const response = await axiosClient.post('/templates/', {
                search_string: searchString,
                merchant_name: merchantName
            });
            setTemplates(prev => [...prev, response.data]);
            return response.data;
        } catch (err) {
            setError(err.response?.data?.error || 'Failed to create template');
            throw err;
        } finally {
            setLoading(false);
        }
    };

    const deleteTemplate = async (id) => {
        setLoading(true);
        setError(null);
        try {
            await axiosClient.delete(`/templates/${id}/`);
            setTemplates(prev => prev.filter(t => t.id !== id));
        } catch (err) {
            setError(err.response?.data?.error || 'Failed to delete template');
            throw err;
        } finally {
            setLoading(false);
        }
    };

    return {
        templates,
        loading,
        error,
        fetchTemplates,
        createTemplate,
        deleteTemplate
    };
};
