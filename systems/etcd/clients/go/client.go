package main

import (
	"log"
	"time"
	"context"
	"strings"
	"os"
	"strconv"

	zmq "github.com/pebbe/zmq4"
	"go.etcd.io/etcd/clientv3"
	"github.com/golang/protobuf/proto"
	"./OpWire"
)


func unix_seconds(t time.Time) float64 {
	return float64(t.UnixNano()) / 1e9
}

func put(cli *clientv3.Client, op *OpWire.Operation_Put, clientid uint32) *OpWire.Response {
	//println("CLIENT: Attempting to put")
	// TODO implement options
	st := unix_seconds(time.Now())
	_, err := cli.Put(context.Background(), string(op.Put.Key), string(op.Put.Value))
	end := unix_seconds(time.Now())

	err_msg := "None"
	if(err != nil){
		err_msg = err.Error()
	}

	resp := &OpWire.Response {
		ResponseTime:		end-op.Put.Start,
		Err:			err_msg,
		ClientStart:		st,
		QueueStart:		op.Put.Start,
		End:			end,
		Clientid:		clientid,
		Optype:			"Write",
		Target:			cli.ActiveConnection().Target(),
	}

	//println("CLIENT: Successfully put")
	return resp
}

func get(cli *clientv3.Client, op *OpWire.Operation_Get, clientid uint32) *OpWire.Response {
	// TODO implement options
	//println("CLIENT: Attempting to get")
	st := unix_seconds(time.Now())
	_, err := cli.Get(context.Background(), string(op.Get.Key))
	end := unix_seconds(time.Now())

	err_msg := "None"
	if(err != nil){
		err_msg = err.Error()
	}

	resp := &OpWire.Response {
		ResponseTime:		end-op.Get.Start,
		Err:			err_msg,
		ClientStart:		st,
		QueueStart:		op.Get.Start,
		End:			end,
		Clientid:		clientid,
		Optype:			"Read",
		Target:			cli.ActiveConnection().Target(),
	}

	//println("CLIENT:Successfully got")

	return resp
}

func ReceiveOp(socket *zmq.Socket) *OpWire.Operation{
	payload, _ := socket.Recv(0)
	op := &OpWire.Operation{}
	if err := proto.Unmarshal([]byte(payload), op); err != nil {
		log.Fatalln("Failed to parse incomming operation")
	}
	return op
}

func check(e error) {
	if e != nil {
		panic(e)
	}
}

func marshall_response(resp *OpWire.Response) string {
	payload, err := proto.Marshal(resp)
	check(err)
	return string(payload)
}

func main() {
	println("Client: Starting client")

	endpoints := strings.Split(os.Args[1], ",")
	for index, ip := range endpoints {
		name := ip + ":2379"
		println(name)
		endpoints[index] = name
	}

	i, err := strconv.ParseUint(os.Args[2], 10, 32)
	check(err)
	address := "ipc://" + os.Args[3]

	clientid := uint32(i)

	socket, _ := zmq.NewSocket(zmq.REQ)
	defer socket.Close()
	print("Client: connecting to: " + address)
	socket.Connect(address)

	dialTimeout := 2 * time.Second

	cli, err := clientv3.New(clientv3.Config{
		DialTimeout:		dialTimeout,
		DialKeepAliveTime:	dialTimeout/2,
		DialKeepAliveTimeout:	dialTimeout*2,
		AutoSyncInterval:	dialTimeout/2,
		Endpoints:		endpoints,
	})
	defer cli.Close()
	check(err)

	println("Client: Sending ready signal")
	//send ready signal
	socket.Send("",0)

	for {
		println("Client: Waiting to recieve op")
		Operation := ReceiveOp(socket)
		println("Client: Received")

		switch op := Operation.OpType.(type) {
		case *OpWire.Operation_Put:
			resp := put(cli, op, clientid)
			payload := marshall_response(resp)
			socket.Send(payload, 0)

		case *OpWire.Operation_Get:
			resp := get(cli, op, clientid)
			payload := marshall_response(resp)
			socket.Send(payload, 0)

		case *OpWire.Operation_Quit:
			return

		default:
			resp := &OpWire.Response {
				ResponseTime:  -1,
				Err:			"Error: Operation was not found / supported",
				Clientid:		clientid,
				Optype:			"Error",
			}
			payload := marshall_response(resp)
			socket.Send(payload, 0)
		}
	}
}
