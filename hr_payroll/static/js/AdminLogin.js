import React, { useContext, useEffect, useState } from 'react';
import useAuth from './Context/AuthContext';
import useForm from './Hooks/useForm';
import { useNavigate } from 'react-router-dom';
import Modal from './Components/Modal';
import Icon from './Components/Icon';

export default function Login() {
    const { login, auth } = useAuth();
    const [message, setMessage] = useState('');
    const [loading, setLoading] = useState(false);
    const navigate = useNavigate();

    useEffect(() => {
        // Check for Django errors injected into the DOM
        const errorScript = document.getElementById('django-errors');
        if (errorScript) {
            try {
                const errors = JSON.parse(errorScript.textContent);
                let msg = '';
                if (errors.__all__) {
                    msg = errors.__all__[0].message;
                } else {
                    // Just take the first error found
                    const firstKey = Object.keys(errors)[0];
                    if (firstKey && errors[firstKey].length > 0) {
                        msg = errors[firstKey][0].message;
                    }
                }
                if (msg) setMessage(msg);
            } catch (e) {
                console.error("Failed to parse Django errors", e);
            }
        }

        const messageScript = document.getElementById('django-messages');
        if (messageScript) {
            try {
                const messages = JSON.parse(messageScript.textContent);
                if (messages.length > 0) {
                    setMessage(messages[0].message);
                }
            } catch (e) { }
        }
    }, [auth, navigate]);

    const handleLogin = async (formData) => {
        setLoading(true);
        setMessage('');
        try {
            await login(formData.username, formData.password)
        } catch (err) {
            setMessage(err.message || "Login failed");
            setLoading(false);
        }
    };

    const { values, handleChange, handleSubmit } = useForm(
        { username: '', password: '' },
        handleLogin
    );
    const formContainer = (
        <div
            id="form_container"
            className="justify-center flex-1   flex flex-col p-8 dark:bg-slate-800  bg-white text-black"
        >
            <Modal isOpen={loading} location={'center'} >
                <div className="flex items-center justify-center h-screen">
                    <div className="relative">
                        <div className="h-24 w-24 rounded-full border-t-8 border-b-8 border-gray-200"></div>
                        <div className="absolute top-0 left-0 h-24 w-24 rounded-full border-t-8 border-b-8 border-green-600 animate-spin">
                        </div>
                    </div>
                </div></Modal>
            <form
                onSubmit={handleSubmit}
                className="  flex-1 flex flex-col items-center p-7 "
                action=""
            >
                <div className=" flex flex-col justify-center  flex-1 w-full ">
                    <p className="py-2 dark:text-slate-200 flex justify-center font-semibold">
                        Login first to your account
                    </p>
                    <div className="py-2">
                        <label className="w-full dark:text-slate-200 text-xs font-semibold " htmlFor="email">
                            Username <span className="text-red-700">*</span>
                        </label>
                        <input
                            className="my-1 border dark:text-slate-300 dark:border-slate-600 border-gray-300 p-2 rounded w-full"
                            type="text"
                            onChange={handleChange}
                            value={values.username}
                            name="username"
                            id="username"
                            placeholder="enter your username"
                        />
                    </div>
                    <div className="py-2">
                        <label className="w-full dark:text-slate-200 text-xs font-semibold" htmlFor="password">
                            Password <span className="text-red-700">*</span>
                        </label>
                        <input
                            className="my-1 border dark:text-slate-300 dark:border-slate-600 border-gray-300  p-2 rounded w-full"
                            type="password"
                            name="password"
                            onChange={handleChange}
                            value={values.password}
                            id="password"
                            placeholder="enter your password"
                        />
                        {message === '' ? "" :
                            <p className="text-red-500 text-xs ">
                                {message}
                            </p>}
                    </div>
                    <div className="py-2 flex justify-between  w-full">
                        <div className="flex items-center justify-center">
                            <input
                                className=""
                                type="checkbox"
                                name="remember me"
                                id="rememberme"
                            />
                            <p className="px-2 text-xs text-gray-500 font-semibold">
                                Remember Me
                            </p>
                        </div>
                        <p className="inline-flex text-xs text-gray-500 font-semibold">
                            Forgot Password
                        </p>
                    </div>
                    <button
                        type="submit"
                        className="items-center justify-center bg-green-600 hover:bg-green-700 inline-flex px-32 py-2.5 rounded-md text-sm font-semibold text-white transition-colors"
                    >
                        Login
                    </button>
                    <div className="flex items-center gap-1.5 py-2">
                        <hr className="flex-1 dark:text-slate-200 opacity-8" />
                        <p className="py-2 px-2  flex justify-center text-gray-500 text-xs font-semibold">
                            Or login with
                        </p>
                        <hr className="flex-1 dark:text-slate-200 opacity-8" />
                    </div>
                    <div id="Google_Apple" className="py-2 flex justify-evenly w-full">
                        <div className="border inline-flex px-16 py-2  border-gray-300   rounded-md justify-center items-center">
                            <img
                                className="h-4"
                                src="/svg/google-color-svgrepo-com.svg"
                                alt=""
                            />
                            <p className="ml-2.5 dark:text-slate-200 text-sm font-semibold">Google</p>
                        </div>
                        <div className="border  border-gray-300  inline-flex px-16 py-2 rounded-md justify-center items-center">
                            <Icon name="Github" className="text-slate-700 dark:text-slate-300 fill-slate-700 dark:fill-slate-300" />
                            <p className="ml-2.5 dark:text-slate-200 text-sm font-semibold">GitHub</p>
                        </div>
                    </div>
                    <p className=" py-2 flex justify-center text-gray-500 text-xs">
                        You're new in here?
                        <span className="text-green-900 font-semibold">Create Account</span>
                    </p>
                </div>
            </form>
            <p className=" flex justify-center text-xs font-light text-gray-500">
                ©20l5 HR Dashboard Alright required.{' '}
                <span className="font-semibold">Terms & Conditione Privacy Policy</span>
            </p>
        </div>
    );
    const image_div = (
        <div
            id="image_div"
            className=" sm:hidden md:hidden lg:flex flex-col flex-1"
            style={{ backgroundColor: '#121828' }}
        >
            <img src="/static/images/admin_login_image.png" alt="hr" className="flex-3 overflow-hidden object-cover" />
            <div className="p-5 flex-1 border-t-4 border-green-600">
                <p className="text-xs font-semibold text-white">HR Dashboard</p>
                <p className="text-4xl font-semibold py-2 text-white">
                    Let's empower your employees today.
                </p>
                <p className="text-xs text-gray-400">
                    we help to complete all your conveyencing needs easily
                </p>
            </div>
        </div>
    );

    return (
        <div
            className={`  flex-1 py-5 px-48 h-screen dark:bg-slate-950 bg-slate-100 w-full flex justify-center`}
        >
            <div className="flex h-full w-full bg-white sm:flex-col lg:flex-row rounded shadow-lg overflow-hidden">
                {image_div}
                {formContainer}
            </div>
        </div>
    );
}
