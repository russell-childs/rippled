//------------------------------------------------------------------------------
/*
    This file is part of rippled: https://github.com/ripple/rippled
    Copyright (c) 2012, 2013 Ripple Labs Inc.

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

#include "../../BeastConfig.h"

#include <beast/module/core/system/BeforeBoost.h>
#include <boost/bimap.hpp>
#include <boost/bimap/list_of.hpp>
#include <boost/bimap/multiset_of.hpp>
#include <boost/bimap/unordered_set_of.hpp>
#include <boost/optional.hpp>
#include <boost/version.hpp>

#include <ripple/unity/app.h>

#include <ripple/unity/net.h>
#include <ripple/unity/rpcx.h>
#include <ripple/unity/websocket.h>
#include <ripple/common/jsonrpc_fields.h>

// This .cpp will end up including all of the public header
// material in Ripple since it holds the Application object.

#include <ripple/common/seconds_clock.h>
#include <ripple/unity/http.h>
#include <ripple/unity/resource.h>
#include <ripple/unity/sitefiles.h>
#include <ripple/unity/validators.h>

#include <beast/asio/io_latency_probe.h>
#include <beast/cxx14/memory.h>

#include <fstream> // For Application.cpp

#include <ripple/module/app/main/CollectorManager.h>
#include <ripple/module/app/main/CollectorManager.cpp>

#include <ripple/module/app/misc/ProofOfWorkFactory.h>

#include <ripple/module/app/main/NodeStoreScheduler.h>
#include <ripple/module/app/main/NodeStoreScheduler.cpp>

#include <ripple/module/app/main/IoServicePool.h>
#include <ripple/module/app/main/IoServicePool.cpp>

#include <ripple/module/app/main/FatalErrorReporter.h>
#include <ripple/module/app/main/FatalErrorReporter.cpp>

#include <ripple/module/app/rpc/RPCHandler.h>
#include <ripple/module/app/rpc/RPCServerHandler.h>
#include <ripple/module/app/main/RPCHTTPServer.h>
#include <ripple/module/app/main/RPCHTTPServer.cpp>
#include <ripple/module/app/rpc/RPCServerHandler.cpp>
#include <ripple/module/app/rpc/RPCHandler.cpp>

#include <ripple/module/app/websocket/WSConnection.h>

#include <ripple/module/app/tx/TxQueueEntry.h>
#include <ripple/module/app/tx/TxQueueEntry.cpp>
#include <ripple/module/app/tx/TxQueue.h>
#include <ripple/module/app/tx/TxQueue.cpp>

#include <ripple/module/app/websocket/WSServerHandler.h>
#include <ripple/module/app/websocket/WSServerHandler.cpp>
#include <ripple/module/app/websocket/WSConnection.cpp>
#include <ripple/module/app/websocket/WSDoor.h>
#include <ripple/module/app/websocket/WSDoor.cpp>

#include <ripple/common/ResolverAsio.h>

#include <ripple/module/app/node/SqliteFactory.h>
#include <ripple/module/app/node/SqliteFactory.cpp>

#include <ripple/module/app/main/Application.cpp>

#include <ripple/module/app/main/Main.cpp>

//------------------------------------------------------------------------------

namespace ripple {
int run (int argc, char** argv);
}

struct ProtobufLibrary
{
    ~ProtobufLibrary ()
    {
        google::protobuf::ShutdownProtobufLibrary();
    }
};

// Must be outside the namespace for obvious reasons
//
int main (int argc, char** argv)
{
#if defined(__GNUC__) && !defined(__clang__)
    auto constexpr gccver = (__GNUC__ * 100 * 100) +
                            (__GNUC_MINOR__ * 100) +
                            __GNUC_PATCHLEVEL__;

    static_assert (gccver >= 40801,
        "GCC version 4.8.1 or later is required to compile rippled.");
#endif

#ifdef _MSC_VER
    static_assert (_MSC_VER >= 1800,
        "Visual Studio 2013 or later is required to compile rippled.");
#endif

    static_assert (BOOST_VERSION >= 105500,
        "Boost version 1.55 or later is required to compile rippled");
        
    //
    // These debug heap calls do nothing in release or non Visual Studio builds.
    //

    // Checks the heap at every allocation and deallocation (slow).
    //
    //beast::Debug::setAlwaysCheckHeap (false);

    // Keeps freed memory blocks and fills them with a guard value.
    //
    //beast::Debug::setHeapDelayedFree (false);

    // At exit, reports all memory blocks which have not been freed.
    //
#if RIPPLE_DUMP_LEAKS_ON_EXIT
    beast::Debug::setHeapReportLeaks (true);
#else
    beast::Debug::setHeapReportLeaks (false);
#endif

    beast::SharedSingleton <ProtobufLibrary>::get ();

    return ripple::run (argc, argv);
}
