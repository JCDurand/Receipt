import { useState, useEffect, useCallback } from 'react';
import { documentService } from '../utils/api';

/* The tags a user can apply (the predefined ones and their own), loaded once,
   and a way to create a new one of their own. */
export const useTags = () => {
    const [tags, setTags] = useState([]);
    const [error, setError] = useState(null);

    useEffect(() => {
        let isMounted = true;

        documentService
            .getTags()
            .then((data) => {
                if (isMounted) setTags(data || []);
            })
            .catch((err) => {
                console.error('Failed to load tags', err);
                if (isMounted) setError('Failed to load tags.');
            });

        return () => {
            isMounted = false;
        };
    }, []);

    /* Resolves with the new tag, which is then available to every picker */
    const createTag = useCallback(async (name) => {
        const tag = await documentService.createTag(name);
        setTags((prev) => [...prev, tag]);
        return tag;
    }, []);

    return { tags, error, createTag };
};
