import { useState } from 'react';

const useForm = (initialValues, callback) => {
    const [values, setValues] = useState(initialValues);

    const handleChange = (e) => {
        const { name, value } = e.target;
        setValues({
            ...values,
            [name]: value,
        });
    };

    const handleSubmit = (e) => {
        e.preventDefault();
        callback(values);
    };

    return {
        values,
        handleChange,
        handleSubmit,
    };
};

export default useForm;
