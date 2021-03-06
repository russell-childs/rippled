//------------------------------------------------------------------------------
/*
    This file is part of rippled: https://github.com/ripple/rippled
    Copyright (c) 2012-2014 Ripple Labs Inc.

    Permission to use, copy, modify, and/or distribute this software for any
    purpose  with  or without fee is hereby granted, provided that the above
    copyright notice and this permission notice appear in all copies.

    THE  SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
    WITH  REGARD  TO  THIS  SOFTWARE  INCLUDING  ALL  IMPLIED  WARRANTIES  OF
    MERCHANTABILITY  AND  FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
    ANY  SPECIAL ,  DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
    WHATSOEVER  RESULTING  FROM  LOSS  OF USE, DATA OR PROFITS, WHETHER IN AN
    ACTION  OF  CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
    OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
*/
//==============================================================================

#include <ripple/module/rpc/impl/ParseAccountIds.h>

namespace ripple {
namespace RPC {

boost::unordered_set<RippleAddress> parseAccountIds (const Json::Value& jvArray)
{
    boost::unordered_set<RippleAddress> usnaResult;

    for (Json::Value::const_iterator it = jvArray.begin (); it != jvArray.end (); it++)
    {
        RippleAddress   naString;

        if (! (*it).isString () || !naString.setAccountID ((*it).asString ()))
        {
            usnaResult.clear ();
            break;
        }
        else
        {
            (void) usnaResult.insert (naString);
        }
    }

    return usnaResult;
}

} // RPC
} // ripple
