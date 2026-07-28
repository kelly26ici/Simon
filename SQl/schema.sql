-- customer_profiles table
CREATE TABLE customer_profiles (
    whatsapp_id TEXT PRIMARY KEY,
    preferred_name TEXT,
    budget_range TEXT,
    preferred_area TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- mpesa_transactions table
CREATE TABLE mpesa_transactions (
    checkout_request_id TEXT PRIMARY KEY,
    merchant_request_id TEXT,
    phone_number TEXT,
    amount NUMERIC,
    state TEXT,
    account_reference TEXT,
    mpesa_receipt TEXT,
    result_desc TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- properties table
CREATE TABLE properties (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT,
    location TEXT,
    price NUMERIC,
    bedrooms INTEGER,
    availability TEXT,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
