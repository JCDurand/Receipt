import { useState, useEffect } from 'react';
import axiosClient from '../api/axiosClient';

export const useTransactions = () => {
    const [transactions, setTransactions] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const fetchTransactions = async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await axiosClient.get('/');
            setTransactions(response.data);
        } catch (err) {
            console.error("Error fetching transactions:", err);
            setError("Failed to load transactions.");
        } finally {
            setLoading(false);
        }
    };

    /* Fetch transactions when this hook first mounts. */
    useEffect(() => {
        fetchTransactions();
    }, []);

    /* Return the data + a refetch function so components can refresh manually if needed. */
    return { transactions, loading, error, refetch: fetchTransactions };
};
