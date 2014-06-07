//This file contains unit tests that are executed in response to a test message.
//The test message that this file is written against is: Ripple_Labs_Test_Message_TMGetObjectByHash
//This test message is declared in the *.proto file in this directory.
//The unit tests in this file shall:
// a. Send a request for a compact fetch pack and verify that the request is received
// b. Receive a reply to the request for a compact fetch pack and verify that the compact fetch pack is received.
// c. Verify that the contents of the compact fetch pack are precisely the difference in leaf nodes between
//      the source ledger and wanted ledger account state and transaction tree maps.
// d. Verify that the wanted ledger account state and transaction tree maps are correctly built from the
//      source ledger trees and compact fetch pack. Verification shall succeed if and only if the hash of the generated ledger
//      is exactly equal to the hash of the wanted ledger.
// e. Verify that existing functionality for the sending of full fetch pack requests, receipt of full fetch pack replies and
//      processing of full fetch packs is unchanged by the code introduced for compact fetch packs, in other words, there shall be a
//      test or tests verifying that nothing has been broken.

//Preliminary sketch:

// 1. Apply code from typical unit test, e.g. bind_handler.test.cpp, in building a compact fetch pack specific set of unit tests.

// 2. Re-use code from LedgerMaster.cpp to send test message

/*
     void getFetchPack (Ledger::ref nextLedger)
    {
        Peer::ptr target;
        int count = 0;

        Overlay::PeerSequence peerList = getApp().overlay ().getActivePeers ();
        for (auto const& peer : peerList)
        {
            if (peer->hasRange (nextLedger->getLedgerSeq() - 1, nextLedger->getLedgerSeq()))
            {
                if (count++ == 0)
                    target = peer;
                else if ((rand () % ++count) == 0)
                    target = peer;
            }
        }

        if (target)
        {
            protocol::TMGetObjectByHash tmBH;
            tmBH.set_query (true);
            tmBH.set_type (protocol::TMGetObjectByHash::otFETCH_PACK);
            tmBH.set_ledgerhash (nextLedger->getHash().begin (), 32);
            Message::pointer packet = boost::make_shared<Message> (tmBH, protocol::mtGET_OBJECTS);

            target->sendPacket (packet, false);
            WriteLog (lsTRACE, LedgerMaster) << "Requested fetch pack for " << nextLedger->getLedgerSeq() - 1;
        }
        else
            WriteLog (lsDEBUG, LedgerMaster) << "No peer for fetch pack";
    }
 */

// 3. TODO: Find root of code that handles a reply for a full fetch pack request and utilise it  in this system test.


